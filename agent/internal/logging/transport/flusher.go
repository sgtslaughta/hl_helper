package transport

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"sync"
	"sync/atomic"
	"time"

	"github.com/hlhelper/hl-agent/internal/logtypes"
	"github.com/hlhelper/hl-agent/internal/logging"
	"github.com/hlhelper/hl-agent/proto/fleet/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// Policy mirrors the protobuf LogPolicy, wrapped for atomic.Pointer compatibility.
type Policy struct {
	Version           uint32
	DefaultLevel      string
	BatchMaxBytes     uint32
	BatchMaxIntervalS uint32
	DefaultSampleRate float64
	BackoffMs         uint32
}

// Config configures a Flusher.
type Config struct {
	Emitter      *logging.Emitter
	Dict         *Dictionary
	Sampler      *Sampler
	Coalescer    *Coalescer
	Policy       *atomic.Pointer[Policy] // pointer to allow passing by reference
	Now          func() time.Time
	MinForcedGap time.Duration
}

// Flusher packs events from the emitter's buffer into a protobuf LogBatch for
// piggyback on the heartbeat. It applies sampling, coalescing, gzip per-entry,
// and respects the active LogPolicy.
type Flusher struct {
	em          *logging.Emitter
	dict        *Dictionary
	sampler     *Sampler
	coalescer   *Coalescer
	policyPtr   *atomic.Pointer[Policy]
	now         func() time.Time
	minForcedGap time.Duration

	mu          sync.Mutex
	lastForced  time.Time
	lastSeq     uint64 // highest seq successfully acked
}

// NewFlusher creates a new Flusher with the given config.
func NewFlusher(cfg Config) *Flusher {
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	if cfg.MinForcedGap == 0 {
		cfg.MinForcedGap = 5 * time.Second
	}

	policyPtr := cfg.Policy
	if policyPtr == nil {
		policyPtr = &atomic.Pointer[Policy]{}
	}

	return &Flusher{
		em:           cfg.Emitter,
		dict:         cfg.Dict,
		sampler:      cfg.Sampler,
		coalescer:    cfg.Coalescer,
		policyPtr:    policyPtr,
		now:          cfg.Now,
		minForcedGap: cfg.MinForcedGap,
	}
}

// Build assembles a LogBatch + any new dictionary entries to register.
// Caller is responsible for sending the dict (if non-nil) before sending the batch.
// Returns (batch=nil, dict=nil, lastEmittedSeq=0, sampledOutThroughSeq=0, err=nil) when nothing pending.
//
// build details:
//  1. Read BatchMaxBytes from policy (default 65536 if zero).
//  2. Read up to 4096 oldest events from buffer.
//  3. For each event in order:
//     - If sampler says skip, don't add to batch but track as sampled-out seq.
//     - Push to coalescer; if returns events, those become candidates to emit.
//     - For each candidate: gzip-marshal its JSON payload, intern strings via Dict,
//       build pb.LogEntry, track size. If size > maxBytes, break (don't include; get next round).
//     - If level in {error, critical} → forced = true.
//  4. If forced && time.Since(lastForced) < MinForcedGap → forced = false (rate-limited).
//  5. If forced, update lastForced = now.
//  6. dict = Dict.Delta() packed as pb.LogDictionary if non-empty, else nil.
//  7. Return assembled pb.LogBatch{Entries, FirstSeq, LastSeq, OverflowFlush=forced, DictVersion}.
func (f *Flusher) Build(forced bool) (*v1.LogBatch, *v1.LogDictionary, uint64, uint64, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	// Get current policy or use zero-value defaults
	policy := f.policyPtr.Load()
	maxBytes := uint32(65536)
	if policy != nil && policy.BatchMaxBytes > 0 {
		maxBytes = policy.BatchMaxBytes
	}

	// Read up to 4096 oldest events from buffer
	events, err := f.em.Buffer().PeekFrom(f.lastSeq, 4096)
	if err != nil {
		return nil, nil, 0, 0, err
	}

	if len(events) == 0 {
		return nil, nil, 0, 0, nil
	}

	// Prepare to accumulate entries and track sequences
	var entries []*v1.LogEntry
	var currentSize uint32
	var firstSeq, lastEmittedSeq, sampledOutThroughSeq uint64
	overflowFlush := forced

	for i, ev := range events {
		// Check if sampler wants to drop this event
		if !f.sampler.Keep(ev) {
			sampledOutThroughSeq = ev.Event.Sequence
			continue
		}

		// Push to coalescer; if returns events, those are candidates to emit
		candidates := f.coalescer.Push(ev)
		if candidates == nil {
			// Event merged into coalescer; don't emit yet
			sampledOutThroughSeq = ev.Event.Sequence
			continue
		}

		// For each candidate, try to add to batch
		for _, candidate := range candidates {
			entry, err := f.buildLogEntry(candidate)
			if err != nil {
				return nil, nil, 0, 0, err
			}

			// Estimate size (payload + envelope overhead)
			entrySize := uint32(len(entry.Payload)) + 40

			// Check if adding this entry would exceed maxBytes
			if currentSize > 0 && currentSize+entrySize > maxBytes {
				// Batch is full; break out and let next Build pick this up
				break
			}

			// Add entry to batch
			entries = append(entries, entry)
			currentSize += entrySize
			lastEmittedSeq = entry.Seq

			if firstSeq == 0 {
				firstSeq = entry.Seq
			}

			// Check if entry level triggers forced flush
			if entry.Level == "error" || entry.Level == "critical" {
				overflowFlush = true
			}
		}

		sampledOutThroughSeq = ev.Event.Sequence

		// Update lastSeq if we've moved forward
		if i < len(events)-1 {
			f.lastSeq = ev.Event.Sequence
		}
	}

	// Flush any pending entry in coalescer for final Build
	if len(entries) == 0 || (len(entries) > 0 && entries[len(entries)-1].Seq != events[len(events)-1].Event.Sequence) {
		pending := f.coalescer.Flush()
		if len(pending) > 0 {
			for _, candidate := range pending {
				entry, err := f.buildLogEntry(candidate)
				if err != nil {
					return nil, nil, 0, 0, err
				}

				entrySize := uint32(len(entry.Payload)) + 40
				if currentSize > 0 && currentSize+entrySize > maxBytes {
					break
				}

				entries = append(entries, entry)
				currentSize += entrySize
				lastEmittedSeq = entry.Seq

				if firstSeq == 0 {
					firstSeq = entry.Seq
				}

				if entry.Level == "error" || entry.Level == "critical" {
					overflowFlush = true
				}
			}
		}
	}

	// If no entries were emitted, return nil batch
	if len(entries) == 0 {
		// But still return sampledOutThroughSeq so caller can ack those drops
		return nil, nil, 0, sampledOutThroughSeq, nil
	}

	// Rate-limit overflow flush
	if overflowFlush {
		now := f.now()
		if !f.lastForced.IsZero() && now.Sub(f.lastForced) < f.minForcedGap {
			overflowFlush = false
		} else {
			f.lastForced = now
		}
	}

	// Pack dictionary delta
	var dictPb *v1.LogDictionary
	dictDelta := f.dict.Delta()
	if len(dictDelta) > 0 {
		dictPb = &v1.LogDictionary{
			Version: f.dict.Version(),
			Strings: dictDelta,
		}
	}

	// Assemble LogBatch
	batch := &v1.LogBatch{
		Entries:       entries,
		FirstSeq:      firstSeq,
		LastSeq:       lastEmittedSeq,
		OverflowFlush: overflowFlush,
		DictVersion:   f.dict.Version(),
	}

	// Update lastSeq with the highest sequence we've seen (including sampler-dropped)
	if sampledOutThroughSeq > f.lastSeq {
		f.lastSeq = sampledOutThroughSeq
	}

	return batch, dictPb, lastEmittedSeq, sampledOutThroughSeq, nil
}

// buildLogEntry converts a logtypes.Event to a pb.LogEntry with gzipped payload.
func (f *Flusher) buildLogEntry(ev logtypes.Event) (*v1.LogEntry, error) {
	// Intern action, category, logger strings to track them in the dictionary
	_, _ = f.dict.Intern(ev.Event.Action)
	if len(ev.Event.Category) > 0 {
		_, _ = f.dict.Intern(ev.Event.Category[0])
	}
	_, _ = f.dict.Intern(ev.Log.Logger)

	// Gzip-marshal the event JSON
	payload, err := gzipMarshal(ev)
	if err != nil {
		return nil, err
	}

	category := ""
	if len(ev.Event.Category) > 0 {
		category = ev.Event.Category[0]
	}

	// Build LogEntry
	entry := &v1.LogEntry{
		Seq:      ev.Event.Sequence,
		Ts:       timestamppb.New(ev.TS),
		Level:    ev.Log.Level,
		Action:   ev.Event.Action,
		Category: category,
		Outcome:  ev.Event.Outcome,
		Payload:  payload,
	}

	return entry, nil
}

// Ack tells the flusher the server persisted up to throughSeq.
func (f *Flusher) Ack(throughSeq uint64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.lastSeq = throughSeq
	return f.em.Buffer().Ack(throughSeq)
}

// SetPolicy hot-swaps the active policy.
func (f *Flusher) SetPolicy(p *Policy) {
	f.policyPtr.Store(p)
}

// gzipMarshal marshals an event to JSON and gzip-compresses it.
func gzipMarshal(ev logtypes.Event) ([]byte, error) {
	jsonData, err := json.Marshal(ev)
	if err != nil {
		return nil, err
	}

	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	if _, err := gz.Write(jsonData); err != nil {
		return nil, err
	}
	if err := gz.Close(); err != nil {
		return nil, err
	}

	return buf.Bytes(), nil
}
