package buffer_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/hlhelper/hl-agent/internal/logging"
	"github.com/hlhelper/hl-agent/internal/logging/buffer"
)

func TestEmitWritesToBuffer(t *testing.T) {
	dir := t.TempDir()
	em, err := buffer.New(buffer.Config{
		BufferPath:   filepath.Join(dir, "logs.db"),
		AgentID:      "a",
		SessionID:    "s",
		HostID:       "h",
		HostName:     "n",
		AgentVer:     "0.4.1",
		FallbackFile: filepath.Join(dir, "fallback.log"),
	})
	if err != nil {
		t.Fatal(err)
	}
	defer em.Close()
	em.Emit(logging.LevelInfo, "task", "task.exec.completed", "ok", map[string]any{"rc": 0})
	if em.PendingCount() != 1 {
		t.Fatalf("want 1 pending, got %d", em.PendingCount())
	}
}

func TestEmitSequenceMonotonic(t *testing.T) {
	dir := t.TempDir()
	em, _ := buffer.New(buffer.Config{
		BufferPath:   filepath.Join(dir, "l.db"),
		AgentID:      "a",
		SessionID:    "s",
		HostID:       "h",
		FallbackFile: filepath.Join(dir, "fb.log"),
	})
	defer em.Close()
	for i := 0; i < 5; i++ {
		em.Emit(logging.LevelInfo, "task", "x", "m", nil)
	}
	out, _ := em.Buffer().PeekFrom(0, 10)
	if len(out) != 5 {
		t.Fatalf("want 5 got %d", len(out))
	}
	for i := uint64(0); i < 5; i++ {
		if out[i].Event.Sequence != i+1 {
			t.Fatalf("seq %d want %d", out[i].Event.Sequence, i+1)
		}
	}
}

func TestEmitErrPopulatesErrorFields(t *testing.T) {
	dir := t.TempDir()
	em, _ := buffer.New(buffer.Config{
		BufferPath:   filepath.Join(dir, "l.db"),
		AgentID:      "a",
		SessionID:    "s",
		HostID:       "h",
		FallbackFile: filepath.Join(dir, "fb.log"),
	})
	defer em.Close()
	em.EmitErr(logging.LevelError, "update", "update.swap.failed", "sig mismatch", "SIG_MISMATCH", "signature did not verify", map[string]any{"from": "0.4.1", "to": "0.4.2"})
	out, _ := em.Buffer().PeekFrom(0, 10)
	if len(out) != 1 {
		t.Fatalf("want 1 got %d", len(out))
	}
	ev := out[0]
	if ev.Error == nil {
		t.Fatal("expected Error field populated")
	}
	if ev.Error.Code != "SIG_MISMATCH" {
		t.Fatalf("code: %s", ev.Error.Code)
	}
	if ev.Log.Level != "error" {
		t.Fatalf("level: %s", ev.Log.Level)
	}
}

func TestEmitPanicIsRecovered(t *testing.T) {
	dir := t.TempDir()
	em, _ := buffer.New(buffer.Config{
		BufferPath:   filepath.Join(dir, "l.db"),
		AgentID:      "a",
		SessionID:    "s",
		HostID:       "h",
		FallbackFile: filepath.Join(dir, "fb.log"),
	})
	defer em.Close()
	// details containing a channel will fail json.Marshal → buffer.Append returns error → emitter must not panic.
	em.Emit(logging.LevelInfo, "task", "x", "msg", map[string]any{"bad": make(chan int)})
	// ensure fallback file got an entry
	info, err := os.Stat(filepath.Join(dir, "fb.log"))
	if err != nil {
		t.Fatal(err)
	}
	if info.Size() == 0 {
		t.Fatal("expected fallback file to have data")
	}
}

func TestPendingCountReflectsBuffer(t *testing.T) {
	dir := t.TempDir()
	em, _ := buffer.New(buffer.Config{
		BufferPath:   filepath.Join(dir, "l.db"),
		AgentID:      "a",
		SessionID:    "s",
		HostID:       "h",
		FallbackFile: filepath.Join(dir, "fb.log"),
	})
	defer em.Close()
	if em.PendingCount() != 0 {
		t.Fatal("want 0")
	}
	em.Emit(logging.LevelInfo, "task", "x", "m", nil)
	em.Emit(logging.LevelInfo, "task", "x", "m", nil)
	if em.PendingCount() != 2 {
		t.Fatalf("want 2, got %d", em.PendingCount())
	}
}
