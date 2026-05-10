package exposure

import (
	"context"
	"testing"

	"github.com/hlhelper/hl-agent/internal/logging"
)

func TestScannerEmitsOnCompletion(t *testing.T) {
	fake := &logging.FakeEmitter{}
	s := &Scanner{
		HostID:     "host1",
		Collectors: []Collector{},
		Emitter:    fake,
	}
	_ = s.Scan(context.Background())
	if len(fake.Events) == 0 {
		t.Fatal("expected at least 1 event")
	}
	ev := fake.Events[0]
	if ev.Action != "exposure.scan.completed" {
		t.Fatalf("want action=exposure.scan.completed, got %s", ev.Action)
	}
	if ev.Category != "posture" {
		t.Fatalf("want category=posture, got %s", ev.Category)
	}
}

func TestScannerWithNilEmitter(t *testing.T) {
	s := &Scanner{
		HostID:     "host1",
		Collectors: []Collector{},
		Emitter:    nil,
	}
	// Should not panic
	_ = s.Scan(context.Background())
}
