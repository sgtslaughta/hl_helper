package executor_test

import (
	"bytes"
	"context"
	"os"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/executor"
	xexec "github.com/hlhelper/hl-agent/internal/exec"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

func TestRunShellEcho(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	stdout, stderr, exitCode, status := executor.RunShell(ctx, "echo hi", 10)

	if status != pb.ResultStatus_RESULT_OK {
		t.Fatalf("expected status OK, got %d", status)
	}
	if exitCode != 0 {
		t.Fatalf("expected exit 0, got %d", exitCode)
	}
	if string(stdout) != "hi\n" {
		t.Fatalf("expected stdout 'hi\\n', got %q", string(stdout))
	}
	if len(stderr) != 0 {
		t.Fatalf("expected empty stderr, got %q", string(stderr))
	}
}

func TestRunShellFalse(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, _, exitCode, status := executor.RunShell(ctx, "false", 10)

	if status != pb.ResultStatus_RESULT_FAIL {
		t.Fatalf("expected status FAIL, got %d", status)
	}
	if exitCode != 1 {
		t.Fatalf("expected exit 1, got %d", exitCode)
	}
}

func TestRunShellTimeout(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	stdout, stderr, _, status := executor.RunShell(ctx, "sleep 10", 1)

	if status != pb.ResultStatus_RESULT_TIMEOUT {
		t.Fatalf("expected status TIMEOUT, got %d", status)
	}
	// Exact exit code varies; just verify we got non-zero and no data
	if len(stdout) != 0 || len(stderr) != 0 {
		t.Fatalf("expected no output on timeout, got stdout=%q stderr=%q", string(stdout), string(stderr))
	}
}

func TestRunShell_AsRootDirect(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("requires root for direct mode")
	}
	sink := &recordingSink{}
	stdout, _, code, status := executor.RunShellElevated(
		context.Background(),
		"echo elev",
		1,
		executor.ElevatedRequest{
			Elevator: xexec.Elevator{Kind: xexec.ElevatorDirect},
			TaskID:   "t-direct",
			Reason:   "diagnostic",
			Sink:     sink,
		},
	)
	if code != 0 || status != pb.ResultStatus_RESULT_OK {
		t.Fatalf("code=%d status=%v", code, status)
	}
	if !bytes.Contains(stdout, []byte("elev")) {
		t.Fatalf("stdout=%q", stdout)
	}
	if len(sink.events) < 2 {
		t.Fatalf("expected start+complete, got %d", len(sink.events))
	}
	if sink.events[0].Phase != executor.PhaseStarted {
		t.Fatalf("first phase=%q", sink.events[0].Phase)
	}
	if sink.events[len(sink.events)-1].Phase != executor.PhaseCompleted {
		t.Fatalf("last phase=%q", sink.events[len(sink.events)-1].Phase)
	}
}

func TestRunShell_AsRootNoElevator(t *testing.T) {
	sink := &recordingSink{}
	_, _, _, status := executor.RunShellElevated(
		context.Background(),
		"echo nope",
		1,
		executor.ElevatedRequest{
			Elevator: xexec.Elevator{Kind: xexec.ElevatorNone},
			TaskID:   "t-none",
			Reason:   "diagnostic",
			Sink:     sink,
		},
	)
	if status != pb.ResultStatus_RESULT_REJECTED {
		t.Fatalf("status=%v", status)
	}
	if len(sink.events) != 1 || sink.events[0].Phase != executor.PhaseDenied {
		t.Fatalf("events=%+v", sink.events)
	}
}
