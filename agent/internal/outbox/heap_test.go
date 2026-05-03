package outbox_test

import (
	"path/filepath"
	"runtime"
	"testing"

	"github.com/hlhelper/hl-agent/internal/outbox"
)

// TestHeapStable_AppendAck exercises the hot path (Append → Peek → Ack) over
// many iterations and asserts heap-in-use does not grow unbounded. Catches
// regressions where buffers, transactions, or cursor state accumulate.
func TestHeapStable_AppendAck(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping heap test in -short mode")
	}

	dir := t.TempDir()
	path := filepath.Join(dir, "out.db")
	key := make([]byte, 32)
	for i := range key {
		key[i] = byte(i)
	}
	o, err := outbox.Open(path, outbox.Options{MasterKey: key, MaxBytes: 64 * 1024 * 1024, MaxEntries: 10_000})
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer o.Close()

	payload := make([]byte, 256)

	// Warm-up: 500 round-trips to amortize first-use allocations.
	for i := 0; i < 500; i++ {
		id, err := o.Append(payload)
		if err != nil {
			t.Fatalf("append: %v", err)
		}
		if err := o.Ack(id); err != nil {
			t.Fatalf("ack: %v", err)
		}
	}

	runtime.GC()
	var before runtime.MemStats
	runtime.ReadMemStats(&before)

	// Measured run: 5_000 round-trips. Each Append does an fsync transaction
	// in bbolt; iteration count tuned for CI runtime <30s.
	for i := 0; i < 5_000; i++ {
		id, err := o.Append(payload)
		if err != nil {
			t.Fatalf("append: %v", err)
		}
		if err := o.Ack(id); err != nil {
			t.Fatalf("ack: %v", err)
		}
	}

	runtime.GC()
	var after runtime.MemStats
	runtime.ReadMemStats(&after)

	// HeapInuse may fluctuate by GC pacing; allow generous slack but cap
	// hard at 2 MiB growth — far above expected ~0 and far below a real leak.
	const slack = 2 * 1024 * 1024
	growth := int64(after.HeapInuse) - int64(before.HeapInuse)
	if growth > slack {
		t.Fatalf("heap grew by %d bytes (>%d) — possible leak; before=%d after=%d",
			growth, slack, before.HeapInuse, after.HeapInuse)
	}
	t.Logf("heap stable: before=%d after=%d delta=%d", before.HeapInuse, after.HeapInuse, growth)
}
