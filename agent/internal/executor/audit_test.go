package executor_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/executor"
)

func TestJSONLSink_AppendsLine(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "elevated.jsonl")
	sink := executor.NewJSONLSink(path, 10*1024*1024) // 10MB rotate

	ev := executor.ElevatedEvent{
		Timestamp: time.Unix(1700000000, 0).UTC(),
		TaskID:    "t-1",
		Binary:    "/bin/ls",
		Args:      []string{"-la"},
		Elevator:  "sudo",
		Reason:    "diagnostic",
		Phase:     executor.PhaseStarted,
	}
	sink.Record(ev)

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var got executor.ElevatedEvent
	if err := json.Unmarshal(data[:len(data)-1], &got); err != nil { // strip trailing \n
		t.Fatal(err)
	}
	if got.TaskID != "t-1" || got.Phase != executor.PhaseStarted {
		t.Fatalf("got=%+v", got)
	}
}

func TestMultiSink_FansOut(t *testing.T) {
	a := &recordingSink{}
	b := &recordingSink{}
	m := executor.NewMultiSink(a, b)
	m.Record(executor.ElevatedEvent{TaskID: "x"})
	if len(a.events) != 1 || len(b.events) != 1 {
		t.Fatalf("a=%d b=%d", len(a.events), len(b.events))
	}
}

func TestJSONLSink_Rotates(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "elevated.jsonl")
	sink := executor.NewJSONLSink(path, 100) // tiny cap to force rotation

	ev := executor.ElevatedEvent{TaskID: "t", Reason: "padding-makes-line-long-enough"}
	for i := 0; i < 5; i++ {
		sink.Record(ev)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected current file: %v", err)
	}
	if _, err := os.Stat(path + ".1"); err != nil {
		t.Fatalf("expected rotated .1: %v", err)
	}
}

type recordingSink struct{ events []executor.ElevatedEvent }

func (r *recordingSink) Record(ev executor.ElevatedEvent) { r.events = append(r.events, ev) }
