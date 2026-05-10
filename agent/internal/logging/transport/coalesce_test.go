package transport

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/logtypes"
)

func makeEvent(action, outcome, level string, details map[string]any) logtypes.Event {
	ev := logtypes.Event{
		TS:         time.Now(),
		ECSVersion: "8.0.0",
		Event: logtypes.EventFields{
			Kind:     "event",
			Category: []string{"process"},
			Action:   action,
			Outcome:  outcome,
			Sequence: 1,
			ID:       "id-1",
		},
		Agent: logtypes.AgentFields{
			ID:        "agent-1",
			Type:      "agent",
			SessionID: "sess-1",
		},
		Host: logtypes.HostFields{
			ID:   "host-1",
			Name: "localhost",
		},
		Log: logtypes.LogFields{
			Level:  level,
			Logger: "test",
		},
		Details: details,
	}
	return ev
}

func eventDetailsHash(details map[string]any) string {
	b, _ := json.Marshal(details)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}

func TestCoalescerCollapsesDuplicates(t *testing.T) {
	now := time.Now()
	var clockPos int
	clockTimes := []time.Time{now, now, now, now, now, now}

	c := &Coalescer{
		Window: 1 * time.Second,
		Now: func() time.Time {
			if clockPos >= len(clockTimes) {
				return clockTimes[len(clockTimes)-1].Add(2 * time.Second)
			}
			t := clockTimes[clockPos]
			clockPos++
			return t
		},
	}

	details := map[string]any{"foo": "bar"}
	ev := makeEvent("start", "success", "info", details)

	// Push 5 identical events
	var results []logtypes.Event
	for i := 0; i < 5; i++ {
		out := c.Push(ev)
		results = append(results, out...)
	}

	// No emission on individual pushes
	if len(results) > 0 {
		t.Fatalf("expected no emission during coalescing, got %d events", len(results))
	}

	// Flush should emit 1 event with repeat=5
	flushed := c.Flush()
	if len(flushed) != 1 {
		t.Fatalf("expected 1 event on flush, got %d", len(flushed))
	}

	final := flushed[0]
	if final.Details == nil {
		final.Details = make(map[string]any)
	}

	repeat, ok := final.Details["event.repeat"]
	if !ok || repeat != int64(5) {
		t.Fatalf("expected event.repeat=5, got %v", repeat)
	}

	if final.Details["event.first_ts"] == nil {
		t.Error("expected event.first_ts in Details")
	}
	if final.Details["event.last_ts"] == nil {
		t.Error("expected event.last_ts in Details")
	}
}

func TestCoalescerEmitsOnKeyChange(t *testing.T) {
	now := time.Now()
	var clockPos int
	clockTimes := []time.Time{
		now,       // push A[0]
		now,       // push A[1]
		now,       // push A[2]
		now,       // push B (displaces A, should return [A])
		now.Add(2 * time.Second), // for flush
	}

	c := &Coalescer{
		Window: 1 * time.Second,
		Now: func() time.Time {
			if clockPos >= len(clockTimes) {
				return clockTimes[len(clockTimes)-1].Add(2 * time.Second)
			}
			t := clockTimes[clockPos]
			clockPos++
			return t
		},
	}

	details1 := map[string]any{"foo": "bar"}
	ev1 := makeEvent("start", "success", "info", details1)

	details2 := map[string]any{"foo": "baz"}
	ev2 := makeEvent("stop", "success", "info", details2) // different action

	// Push 3x event A
	for i := 0; i < 3; i++ {
		out := c.Push(ev1)
		if len(out) > 0 {
			t.Fatalf("expected no emission for A[%d], got %d events", i, len(out))
		}
	}

	// Push event B (different key) — should emit A with repeat=3
	out := c.Push(ev2)
	if len(out) != 1 {
		t.Fatalf("expected 1 event (A) when pushing different key, got %d", len(out))
	}

	emitted := out[0]
	repeat, ok := emitted.Details["event.repeat"]
	if !ok || repeat != int64(3) {
		t.Fatalf("expected emitted A with event.repeat=3, got %v", repeat)
	}

	// Flush should emit B with repeat=1
	flushed := c.Flush()
	if len(flushed) != 1 {
		t.Fatalf("expected 1 event (B) on flush, got %d", len(flushed))
	}
	if flushed[0].Event.Action != "stop" {
		t.Fatalf("expected B (stop), got %s", flushed[0].Event.Action)
	}
	repeat, ok = flushed[0].Details["event.repeat"]
	if !ok || repeat != int64(1) {
		t.Fatalf("expected B with event.repeat=1, got %v", repeat)
	}
}

func TestCoalescerFlushesAfterWindow(t *testing.T) {
	now := time.Now()
	var clockPos int
	clockTimes := []time.Time{
		now,                       // push A
		now.Add(2 * time.Second),  // push B — should emit A (window expired)
		now.Add(3 * time.Second),  // for flush
	}

	c := &Coalescer{
		Window: 1 * time.Second,
		Now: func() time.Time {
			if clockPos >= len(clockTimes) {
				return clockTimes[len(clockTimes)-1].Add(2 * time.Second)
			}
			t := clockTimes[clockPos]
			clockPos++
			return t
		},
	}

	details1 := map[string]any{"foo": "bar"}
	ev1 := makeEvent("start", "success", "info", details1)

	details2 := map[string]any{"foo": "bar"} // same details but different ts
	ev2 := makeEvent("start", "success", "info", details2)

	// Push A at time 0
	out1 := c.Push(ev1)
	if len(out1) > 0 {
		t.Fatalf("expected no emission for A, got %d events", len(out1))
	}

	// Push B at time +2s (past the 1s window) — should emit A
	out2 := c.Push(ev2)
	if len(out2) != 1 {
		t.Fatalf("expected 1 event (A) when window expires, got %d", len(out2))
	}

	if out2[0].Event.Action != "start" {
		t.Fatalf("expected A (start), got %s", out2[0].Event.Action)
	}

	repeat, ok := out2[0].Details["event.repeat"]
	if !ok || repeat != int64(1) {
		t.Fatalf("expected A with event.repeat=1, got %v", repeat)
	}

	// Flush should emit B
	flushed := c.Flush()
	if len(flushed) != 1 {
		t.Fatalf("expected 1 event (B) on flush, got %d", len(flushed))
	}
}

func TestCoalescerPassthroughDistinctEvents(t *testing.T) {
	now := time.Now()
	var clockPos int
	clockTimes := []time.Time{now, now, now, now}

	c := &Coalescer{
		Window: 1 * time.Second,
		Now: func() time.Time {
			if clockPos >= len(clockTimes) {
				return clockTimes[len(clockTimes)-1].Add(2 * time.Second)
			}
			t := clockTimes[clockPos]
			clockPos++
			return t
		},
	}

	details1 := map[string]any{"x": 1}
	details2 := map[string]any{"x": 2}
	details3 := map[string]any{"x": 3}

	ev1 := makeEvent("task1", "success", "info", details1)
	ev2 := makeEvent("task2", "success", "info", details2)
	ev3 := makeEvent("task3", "success", "info", details3)

	// Push 3 distinct events. Each new key displaces the previous one.
	// Expected: Push ev1 → no emit. Push ev2 → emit ev1. Push ev3 → emit ev2.
	out1 := c.Push(ev1)
	if len(out1) != 0 {
		t.Fatalf("expected no emission for first event, got %d", len(out1))
	}

	out2 := c.Push(ev2)
	if len(out2) != 1 {
		t.Fatalf("expected 1 event on push ev2, got %d", len(out2))
	}
	if out2[0].Event.Action != "task1" {
		t.Fatalf("expected task1 to be displaced, got %s", out2[0].Event.Action)
	}

	out3 := c.Push(ev3)
	if len(out3) != 1 {
		t.Fatalf("expected 1 event on push ev3, got %d", len(out3))
	}
	if out3[0].Event.Action != "task2" {
		t.Fatalf("expected task2 to be displaced, got %s", out3[0].Event.Action)
	}

	// Flush should emit the final pending (task3)
	flushed := c.Flush()
	if len(flushed) != 1 {
		t.Fatalf("expected 1 event on flush, got %d", len(flushed))
	}
	if flushed[0].Event.Action != "task3" {
		t.Fatalf("expected task3 on flush, got %s", flushed[0].Event.Action)
	}
}
