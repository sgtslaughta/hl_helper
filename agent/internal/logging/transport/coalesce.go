package transport

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"time"

	"github.com/hlhelper/hl-agent/internal/logtypes"
)

// Coalescer collapses identical-shape events arriving within a time window.
// Identity key = (action, outcome, level, sha256(details_json)).
type Coalescer struct {
	Window time.Duration           // default 1s
	Now    func() time.Time         // injected clock, default time.Now
	key    string                   // current pending key (one at a time)
	entry  *coalesceEntry          // current pending entry
}

type coalesceEntry struct {
	event   logtypes.Event
	firstTS time.Time
	lastTS  time.Time
	count   int64
}

func (c *Coalescer) init() {
	if c.Now == nil {
		c.Now = time.Now
	}
	if c.Window == 0 {
		c.Window = 1 * time.Second
	}
}

func (c *Coalescer) identityKey(ev logtypes.Event) string {
	b, _ := json.Marshal(ev.Details)
	h := sha256.Sum256(b)
	hash := hex.EncodeToString(h[:])

	// key = (action, outcome, level, hash)
	key := ev.Event.Action + "|" + ev.Event.Outcome + "|" + ev.Log.Level + "|" + hash
	return key
}

// Push returns events to emit. The coalescer holds ONE pending entry at a time.
// Identical-shape events (same identity key) are coalesced: count increments, timestamps update.
// When a new distinct key arrives:
//   - If there's a pending entry with a different key, emit it (displacement or window expiry check)
//   - Store the new event as pending
//   - Return the emitted entries (or empty if none)
func (c *Coalescer) Push(ev logtypes.Event) []logtypes.Event {
	c.init()

	now := c.Now()
	newKey := c.identityKey(ev)

	// If no pending entry, store and return nil
	if c.entry == nil {
		c.key = newKey
		c.entry = &coalesceEntry{
			event:   ev,
			firstTS: now,
			lastTS:  now,
			count:   1,
		}
		return nil
	}

	// Check if it's the same key (duplicate)
	if c.key == newKey {
		// Same key: coalesce if still in window
		if now.Sub(c.entry.firstTS) < c.Window {
			c.entry.lastTS = now
			c.entry.count++
			return nil
		}

		// Window expired: emit the old one and store the new
		emitted := c.emitEntry(c.entry)
		c.key = newKey
		c.entry = &coalesceEntry{
			event:   ev,
			firstTS: now,
			lastTS:  now,
			count:   1,
		}
		return []logtypes.Event{emitted}
	}

	// Different key: emit pending entry (either due to window expiry or displacement)
	emitted := []logtypes.Event{c.emitEntry(c.entry)}

	// Store the new event
	c.key = newKey
	c.entry = &coalesceEntry{
		event:   ev,
		firstTS: now,
		lastTS:  now,
		count:   1,
	}

	return emitted
}

// Flush returns the currently-pending event (if any) and clears state.
func (c *Coalescer) Flush() []logtypes.Event {
	c.init()

	if c.entry == nil {
		return nil
	}

	emitted := c.emitEntry(c.entry)
	c.entry = nil
	c.key = ""
	return []logtypes.Event{emitted}
}

func (c *Coalescer) emitEntry(entry *coalesceEntry) logtypes.Event {
	ev := entry.event
	if ev.Details == nil {
		ev.Details = make(map[string]any)
	}

	if entry.count > 1 {
		ev.Details["event.repeat"] = entry.count
		ev.Details["event.first_ts"] = entry.firstTS.Format(time.RFC3339Nano)
		ev.Details["event.last_ts"] = entry.lastTS.Format(time.RFC3339Nano)
	} else {
		ev.Details["event.repeat"] = int64(1)
	}

	return ev
}
