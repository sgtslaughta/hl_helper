package executor

import (
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// BridgeSink converts ElevatedEvent into AgentToServer.AgentAuditEvent and
// non-blockingly sends it on out. If out is full, the event is dropped — local
// JSONL is the durable record; bridge delivery is best-effort.
type BridgeSink struct{ out chan<- *pb.AgentToServer }

func NewBridgeSink(out chan<- *pb.AgentToServer) *BridgeSink {
	return &BridgeSink{out: out}
}

func (b *BridgeSink) Record(ev ElevatedEvent) {
	msg := &pb.AgentToServer{
		Msg: &pb.AgentToServer_Audit{
			Audit: &pb.AgentAuditEvent{
				Timestamp: timestamppb.New(ev.Timestamp),
				TaskId:    ev.TaskID,
				Binary:    ev.Binary,
				Args:      ev.Args,
				Elevator:  ev.Elevator,
				Reason:    ev.Reason,
				Phase:     string(ev.Phase),
				ExitCode:  int32(ev.ExitCode),
				Error:     ev.Error,
			},
		},
	}
	select {
	case b.out <- msg:
	default:
		// Channel full — drop. JSONL has the record.
	}
}
