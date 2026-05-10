package buffer_test

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/logging"
	"github.com/hlhelper/hl-agent/internal/logging/buffer"
)

func mkEvent(seq uint64) logging.Event {
	return logging.Event{
		TS:         time.Now().UTC(),
		ECSVersion: "8.11",
		Event: logging.EventFields{
			Kind:     "event",
			Category: []string{"task"},
			Action:   "task.exec.completed",
			Sequence: seq,
			ID:       "x",
		},
		Agent:  logging.AgentFields{ID: "a", Type: "hl-agent", SessionID: "s"},
		Host:   logging.HostFields{ID: "h"},
		Log:    logging.LogFields{Level: "info"},
	}
}

func mkOldEvent(seq uint64, age time.Duration) logging.Event {
	ev := mkEvent(seq)
	ev.TS = time.Now().UTC().Add(-age)
	return ev
}

func TestAppendThenDrain(t *testing.T) {
	dir := t.TempDir()
	b, err := buffer.Open(filepath.Join(dir, "logs.db"), buffer.Options{MaxBytes: 1 << 20, MaxAge: 24 * time.Hour})
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	for i := uint64(1); i <= 5; i++ {
		if err := b.Append(mkEvent(i)); err != nil {
			t.Fatal(err)
		}
	}
	out, err := b.PeekFrom(0, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(out) != 5 {
		t.Fatalf("want 5 got %d", len(out))
	}
	if out[0].Event.Sequence != 1 || out[4].Event.Sequence != 5 {
		t.Fatal("FIFO violated")
	}
	if err := b.Ack(5); err != nil {
		t.Fatal(err)
	}
	out2, _ := b.PeekFrom(0, 10)
	if len(out2) != 0 {
		t.Fatalf("want 0 after ack, got %d", len(out2))
	}
}

func TestPeekFromCursor(t *testing.T) {
	dir := t.TempDir()
	b, _ := buffer.Open(filepath.Join(dir, "logs.db"), buffer.Options{MaxBytes: 1 << 20, MaxAge: 24 * time.Hour})
	defer b.Close()
	for i := uint64(1); i <= 5; i++ {
		_ = b.Append(mkEvent(i))
	}
	out, _ := b.PeekFrom(2, 10)
	if len(out) != 3 || out[0].Event.Sequence != 3 {
		t.Fatalf("got first seq %d (want 3)", out[0].Event.Sequence)
	}
}

func TestAckPartial(t *testing.T) {
	dir := t.TempDir()
	b, _ := buffer.Open(filepath.Join(dir, "logs.db"), buffer.Options{MaxBytes: 1 << 20, MaxAge: 24 * time.Hour})
	defer b.Close()
	for i := uint64(1); i <= 5; i++ {
		_ = b.Append(mkEvent(i))
	}
	_ = b.Ack(3)
	out, _ := b.PeekFrom(0, 10)
	if len(out) != 2 || out[0].Event.Sequence != 4 {
		t.Fatalf("after Ack(3) want seqs 4,5 got %v", out)
	}
}

func TestAgeEviction(t *testing.T) {
	dir := t.TempDir()
	b, _ := buffer.Open(filepath.Join(dir, "logs.db"), buffer.Options{MaxBytes: 1 << 20, MaxAge: 1 * time.Second})
	defer b.Close()
	_ = b.Append(mkOldEvent(1, 1*time.Hour))
	_ = b.Append(mkEvent(2))
	out, _ := b.PeekFrom(0, 10)
	if len(out) != 1 || out[0].Event.Sequence != 2 {
		t.Fatalf("expected only seq 2 after age eviction, got %v", out)
	}
	if b.DroppedCount() == 0 {
		t.Fatal("expected dropped count > 0")
	}
}

func TestSizeEviction(t *testing.T) {
	dir := t.TempDir()
	b, _ := buffer.Open(filepath.Join(dir, "logs.db"), buffer.Options{MaxBytes: 4096, MaxAge: 24 * time.Hour})
	defer b.Close()
	for i := uint64(1); i <= 2000; i++ {
		_ = b.Append(mkEvent(i))
	}
	if b.DroppedCount() == 0 {
		t.Fatal("expected drops on tiny bucket")
	}
}

func TestSurvivesReopen(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "logs.db")
	b, _ := buffer.Open(path, buffer.Options{MaxBytes: 1 << 20, MaxAge: 24 * time.Hour})
	_ = b.Append(mkEvent(1))
	b.Close()
	b2, _ := buffer.Open(path, buffer.Options{MaxBytes: 1 << 20, MaxAge: 24 * time.Hour})
	defer b2.Close()
	out, _ := b2.PeekFrom(0, 10)
	if len(out) != 1 || out[0].Event.Sequence != 1 {
		t.Fatal("not durable")
	}
}

func TestCorruptionRotatesAndRecovers(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "logs.db")
	if err := os.WriteFile(path, []byte("not-a-boltdb-file"), 0600); err != nil {
		t.Fatal(err)
	}
	b, err := buffer.Open(path, buffer.Options{MaxBytes: 1 << 20, MaxAge: 24 * time.Hour})
	if err != nil {
		t.Fatalf("recovery failed: %v", err)
	}
	defer b.Close()
	if !b.WasCorrupted() {
		t.Fatal("expected corruption flag")
	}
	// ensure a rotated file exists
	matches, _ := filepath.Glob(path + ".corrupt.*")
	if len(matches) == 0 {
		t.Fatal("expected rotated corrupt file")
	}
}
