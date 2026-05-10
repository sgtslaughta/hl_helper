package transport

import (
	"compress/gzip"
	"encoding/json"
	"io"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/logtypes"
	"github.com/hlhelper/hl-agent/internal/logging"
	"github.com/hlhelper/hl-agent/proto/fleet/v1"
)

func TestFlusherEmptyBuffer(t *testing.T) {
	em, dict, sam, coal := setupFlusher(t)
	defer em.Close()

	cfg := Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sam,
		Coalescer: coal,
		Now:       time.Now,
	}
	f := NewFlusher(cfg)

	batch, d, lastSeq, sampledOut, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}
	if batch != nil {
		t.Errorf("expected nil batch for empty buffer, got %v", batch)
	}
	if d != nil {
		t.Errorf("expected nil dict for empty buffer, got %v", d)
	}
	if lastSeq != 0 {
		t.Errorf("expected lastSeq=0, got %d", lastSeq)
	}
	if sampledOut != 0 {
		t.Errorf("expected sampledOut=0, got %d", sampledOut)
	}
}

func TestFlusherPacksUpToCap(t *testing.T) {
	em, dict, sam, coal := setupFlusher(t)
	defer em.Close()

	cfg := Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sam,
		Coalescer: coal,
		Now:       time.Now,
		MinForcedGap: 5 * time.Second,
	}
	f := NewFlusher(cfg)

	// Emit many large events
	payload := make([]byte, 1000) // 1KB per event
	for i := 0; i < 100; i++ {
		em.Emit(logtypes.LevelInfo, "test", "action", "msg", map[string]any{"data": payload})
	}

	batch, _, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}
	if batch == nil {
		t.Fatal("expected non-nil batch")
	}

	// Verify batch size is reasonable (should not exceed default maxBytes + overhead)
	batchSize := estimateBatchSize(batch)
	defaultMaxBytes := uint32(65536)
	if batchSize > defaultMaxBytes {
		t.Errorf("batch size %d exceeds limit %d", batchSize, defaultMaxBytes)
	}

	// Verify entries are ordered by seq
	for i := 1; i < len(batch.Entries); i++ {
		if batch.Entries[i].Seq <= batch.Entries[i-1].Seq {
			t.Errorf("entries not ordered: seq[%d]=%d, seq[%d]=%d", i-1, batch.Entries[i-1].Seq, i, batch.Entries[i].Seq)
		}
	}
}

func TestErrorTriggersOverflowFlush(t *testing.T) {
	em, dict, sam, coal := setupFlusher(t)
	defer em.Close()

	cfg := Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sam,
		Coalescer: coal,
		Now:       time.Now,
		MinForcedGap: 5 * time.Second,
	}
	f := NewFlusher(cfg)

	// Emit one ERROR event
	em.Emit(logtypes.LevelError, "test", "action", "error occurred", nil)

	batch, _, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}
	if batch == nil {
		t.Fatal("expected non-nil batch")
	}
	if !batch.OverflowFlush {
		t.Errorf("expected OverflowFlush=true for ERROR level, got false")
	}
}

func TestOffCycleRateLimited(t *testing.T) {
	em, dict, sam, coal := setupFlusher(t)
	defer em.Close()

	now := time.Now()
	cfg := Config{
		Emitter:      em,
		Dict:         dict,
		Sampler:      sam,
		Coalescer:    coal,
		Now:          func() time.Time { return now },
		MinForcedGap: 5 * time.Second,
	}
	f := NewFlusher(cfg)

	// First forced flush (ERROR event)
	em.Emit(logtypes.LevelError, "test", "action1", "error1", nil)
	batch1, _, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build 1 failed: %v", err)
	}
	if batch1 == nil || !batch1.OverflowFlush {
		t.Errorf("first forced flush should have OverflowFlush=true")
	}

	// Ack the batch
	if err := f.Ack(batch1.LastSeq); err != nil {
		t.Fatalf("Ack failed: %v", err)
	}

	// Second forced flush immediately (within MinForcedGap)
	em.Emit(logtypes.LevelError, "test", "action2", "error2", nil)
	batch2, _, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build 2 failed: %v", err)
	}
	// Should be rate-limited now
	if batch2 != nil && batch2.OverflowFlush {
		t.Errorf("second forced flush within MinForcedGap should not have OverflowFlush=true")
	}
}

func TestAckAdvancesBufferWatermark(t *testing.T) {
	em, dict, sam, coal := setupFlusher(t)
	defer em.Close()

	cfg := Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sam,
		Coalescer: coal,
		Now:       time.Now,
	}
	f := NewFlusher(cfg)

	// Emit 3 events
	em.Emit(logtypes.LevelInfo, "test", "action1", "msg1", nil)
	em.Emit(logtypes.LevelInfo, "test", "action2", "msg2", nil)
	em.Emit(logtypes.LevelInfo, "test", "action3", "msg3", nil)

	// First Build
	batch, _, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}
	if batch == nil || len(batch.Entries) != 3 {
		t.Fatalf("expected 3 entries, got %v", batch)
	}

	// Ack
	if err := f.Ack(batch.LastSeq); err != nil {
		t.Fatalf("Ack failed: %v", err)
	}

	// Second Build should return nil (buffer empty)
	batch2, _, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build 2 failed: %v", err)
	}
	if batch2 != nil {
		t.Errorf("expected nil batch after ack, got %v", batch2)
	}
}

func TestDictDeltaIncludedOnNewInterns(t *testing.T) {
	em, dict, sam, coal := setupFlusher(t)
	defer em.Close()

	cfg := Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sam,
		Coalescer: coal,
		Now:       time.Now,
	}
	f := NewFlusher(cfg)

	// First Build with new interns
	em.Emit(logtypes.LevelInfo, "test", "action1", "msg1", nil)
	batch, d, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}
	if batch == nil {
		t.Fatal("expected non-nil batch")
	}
	if d == nil {
		t.Errorf("expected non-nil dict with new interns")
	}
	if d != nil && len(d.Strings) == 0 {
		t.Errorf("expected non-empty dict strings")
	}

	// Ack the batch
	if err := f.Ack(batch.LastSeq); err != nil {
		t.Fatalf("Ack failed: %v", err)
	}

	// Second Build (same action, no new strings) should return nil dict
	em.Emit(logtypes.LevelInfo, "test", "action1", "msg2", nil)
	batch2, d2, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build 2 failed: %v", err)
	}
	if batch2 == nil {
		t.Fatal("expected non-nil batch")
	}
	if d2 != nil {
		t.Errorf("expected nil dict when no new interns, got %v", d2)
	}
}

func TestSamplerDropDoesNotAdvance(t *testing.T) {
	em, dict, sam, coal := setupFlusher(t)
	defer em.Close()

	// Set up sampler to drop debug level
	sam.Rules = append(sam.Rules, CategoryRule{Category: "test", Drop: true})

	cfg := Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sam,
		Coalescer: coal,
		Now:       time.Now,
	}
	f := NewFlusher(cfg)

	// Emit 3 events that will be sampler-dropped
	em.Emit(logtypes.LevelDebug, "test", "action1", "msg1", nil)
	em.Emit(logtypes.LevelDebug, "test", "action2", "msg2", nil)
	em.Emit(logtypes.LevelDebug, "test", "action3", "msg3", nil)

	// Build should return nil batch but process the sampler-dropped seqs
	batch, _, _, sampledOut, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}
	if batch != nil {
		t.Errorf("expected nil batch for sampler-dropped events, got %v", batch)
	}
	if sampledOut == 0 {
		t.Errorf("expected sampledOut > 0 for processed sampler-dropped seqs, got 0")
	}

	// Ack with max(serverAck, sampledOut) should clear the buffer
	if err := f.Ack(sampledOut); err != nil {
		t.Fatalf("Ack failed: %v", err)
	}

	// Next Build should find empty buffer
	batch2, _, _, _, err := f.Build(false)
	if err != nil {
		t.Fatalf("Build 2 failed: %v", err)
	}
	if batch2 != nil {
		t.Errorf("expected nil batch after acking sampler-dropped seqs, got %v", batch2)
	}
}

// Helper functions

func setupFlusher(t *testing.T) (*logging.Emitter, *Dictionary, *Sampler, *Coalescer) {
	cfg := logging.Config{
		BufferPath: t.TempDir() + "/test.db",
		AgentID:    "test-agent",
		SessionID:  "test-session",
		HostID:     "test-host",
		HostName:   "test-hostname",
		AgentVer:   "1.0.0",
	}
	em, err := logging.New(cfg)
	if err != nil {
		t.Fatalf("failed to create emitter: %v", err)
	}

	dict := New()
	sam := &Sampler{DefaultRate: 1.0}
	coal := &Coalescer{Window: 1 * time.Second}

	return em, dict, sam, coal
}

func estimateBatchSize(batch *v1.LogBatch) uint32 {
	var size uint32
	for _, entry := range batch.Entries {
		size += uint32(len(entry.Payload)) + 40
	}
	return size
}

func extractPayload(t *testing.T, payload []byte) map[string]any {
	r := &mockReader{data: payload, pos: 0}
	gr, err := gzip.NewReader(r)
	if err != nil {
		t.Fatalf("failed to create gzip reader: %v", err)
	}
	defer gr.Close()

	var data map[string]any
	if err := json.NewDecoder(gr).Decode(&data); err != nil {
		t.Fatalf("failed to decode payload: %v", err)
	}
	return data
}

type mockReader struct {
	data []byte
	pos  int
}

func (m *mockReader) Read(p []byte) (int, error) {
	if m.pos >= len(m.data) {
		return 0, io.EOF
	}
	n := copy(p, m.data[m.pos:])
	m.pos += n
	return n, nil
}

func (m *mockReader) Close() error {
	return nil
}
