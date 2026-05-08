package executor_test

import (
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/executor"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

func TestBridgeSink_EmitsAuditEvent(t *testing.T) {
	ch := make(chan *pb.AgentToServer, 1)
	sink := executor.NewBridgeSink(ch)

	sink.Record(executor.ElevatedEvent{
		Timestamp: time.Unix(1700000000, 0).UTC(),
		TaskID:    "task-42",
		Binary:    "/bin/ls",
		Args:      []string{"-la"},
		Elevator:  "sudo",
		Reason:    "diag",
		Phase:     executor.PhaseStarted,
	})

	select {
	case msg := <-ch:
		audit := msg.GetAudit()
		if audit == nil {
			t.Fatal("expected audit oneof")
		}
		if audit.TaskId != "task-42" {
			t.Fatalf("task_id=%q", audit.TaskId)
		}
		if audit.Phase != "started" {
			t.Fatalf("phase=%q", audit.Phase)
		}
	case <-time.After(time.Second):
		t.Fatal("no message received")
	}
}

func TestBridgeSink_DropsWhenChannelFull(t *testing.T) {
	ch := make(chan *pb.AgentToServer) // unbuffered, no reader
	sink := executor.NewBridgeSink(ch)
	// Should not block; should not panic.
	sink.Record(executor.ElevatedEvent{TaskID: "x"})
}
