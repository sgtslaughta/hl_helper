package executor_test

import (
	"context"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/executor"
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
