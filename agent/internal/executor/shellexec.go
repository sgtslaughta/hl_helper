// Package executor runs shell commands from ServerToAgent commands.
package executor

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"syscall"
	"time"

	xexec "github.com/hlhelper/hl-agent/internal/exec"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

const (
	maxStdoutBytes = 64 * 1024
	maxStderrBytes = 64 * 1024
)

// RunShell executes a shell command using /bin/sh -c and returns stdout, stderr, exit code, and status.
// Context timeout becomes RESULT_TIMEOUT. Exit code 0 = RESULT_OK, non-zero = RESULT_FAIL.
// stdout and stderr are capped at 64 KiB each.
func RunShell(ctx context.Context, command string, timeoutSec int) (stdout, stderr []byte, exitCode int32, status pb.ResultStatus) {
	// Create a context with a timeout if timeoutSec > 0
	if timeoutSec > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, time.Duration(timeoutSec)*time.Second)
		defer cancel()
	}

	cmd := exec.CommandContext(ctx, "/bin/sh", "-c", command)
	// Run sh in its own process group so we can kill the whole tree
	// (subprocesses sh spawned) on timeout — exec.CommandContext only
	// signals the direct child by default.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return nil
		}
		return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	}

	// Use buffers to capture output
	cmd.Stdout = &bytes.Buffer{}
	cmd.Stderr = &bytes.Buffer{}

	// Run the command
	err := cmd.Run()

	// Capture output before checking error
	outData := cmd.Stdout.(*bytes.Buffer).Bytes()
	errData := cmd.Stderr.(*bytes.Buffer).Bytes()

	// Cap output
	if len(outData) > maxStdoutBytes {
		outData = outData[:maxStdoutBytes]
	}
	if len(errData) > maxStderrBytes {
		errData = errData[:maxStderrBytes]
	}

	stdout = outData
	stderr = errData

	// Determine status and exit code
	if err == nil {
		// Command succeeded
		exitCode = 0
		status = pb.ResultStatus_RESULT_OK
		return
	}

	// Check if it's a context deadline exceeded (timeout)
	if ctx.Err() == context.DeadlineExceeded {
		exitCode = -1 // Indicate timeout
		status = pb.ResultStatus_RESULT_TIMEOUT
		return
	}

	// Check if it's an exit error
	if ee, ok := err.(*exec.ExitError); ok {
		exitCode = int32(ee.ExitCode())
		status = pb.ResultStatus_RESULT_FAIL
		return
	}

	// Some other error (shouldn't happen with CommandContext, but be safe)
	exitCode = -1
	status = pb.ResultStatus_RESULT_FAIL
	return
}

// ElevatedRequest carries the runtime context needed to audit + wrap an elevated shell command.
type ElevatedRequest struct {
	Elevator xexec.Elevator
	TaskID   string
	Reason   string
	Sink     AuditSink
}

// RunShellElevated runs `command` under `/bin/sh -c`, wrapped through the elevator.
// Behavior identical to RunShell when ElevatorDirect; with sudo/doas, prepends
// the wrapper. Emits started/completed events to req.Sink. If Elevator.Kind is
// ElevatorNone, returns RESULT_REJECTED and emits a `denied` event without exec.
func RunShellElevated(ctx context.Context, command string, timeoutSec int, req ElevatedRequest) (stdout, stderr []byte, exitCode int32, status pb.ResultStatus) {
	now := time.Now().UTC()
	base := ElevatedEvent{
		Timestamp: now,
		TaskID:    req.TaskID,
		Binary:    "/bin/sh",
		Args:      []string{"-c", command},
		Elevator:  string(req.Elevator.Kind),
		Reason:    req.Reason,
	}

	if req.Elevator.Kind == xexec.ElevatorNone {
		denied := base
		denied.Phase = PhaseDenied
		denied.Error = xexec.ErrNoElevator.Error()
		if req.Sink != nil {
			req.Sink.Record(denied)
		}
		return nil, []byte(xexec.ErrNoElevator.Error()), -1, pb.ResultStatus_RESULT_REJECTED
	}

	started := base
	started.Phase = PhaseStarted
	if req.Sink != nil {
		req.Sink.Record(started)
	}

	if timeoutSec > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, time.Duration(timeoutSec)*time.Second)
		defer cancel()
	}

	bin, args, err := req.Elevator.Wrap("/bin/sh", []string{"-c", command})
	if err != nil {
		denied := base
		denied.Phase = PhaseDenied
		denied.Error = err.Error()
		if req.Sink != nil {
			req.Sink.Record(denied)
		}
		return nil, []byte(err.Error()), -1, pb.ResultStatus_RESULT_REJECTED
	}

	cmd := exec.CommandContext(ctx, bin, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return nil
		}
		return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	}
	cmd.Stdout = &bytes.Buffer{}
	stderrBuf := &bytes.Buffer{}
	cmd.Stderr = stderrBuf

	// Prepend a transparent banner to stderr so operators see exactly what was wrapped.
	banner := fmt.Sprintf("[ELEVATED via=%s] %s -c %q reason=%q\n", req.Elevator.Kind, "/bin/sh", command, req.Reason)
	stderrBuf.WriteString(banner)

	runErr := cmd.Run()

	outData := cmd.Stdout.(*bytes.Buffer).Bytes()
	errData := stderrBuf.Bytes()
	if len(outData) > maxStdoutBytes {
		outData = outData[:maxStdoutBytes]
	}
	if len(errData) > maxStderrBytes {
		errData = errData[:maxStderrBytes]
	}
	stdout = outData
	stderr = errData

	completed := base
	completed.Phase = PhaseCompleted

	if runErr == nil {
		exitCode = 0
		status = pb.ResultStatus_RESULT_OK
	} else if ctx.Err() == context.DeadlineExceeded {
		exitCode = -1
		status = pb.ResultStatus_RESULT_TIMEOUT
		completed.Error = "timeout"
	} else if ee, ok := runErr.(*exec.ExitError); ok {
		exitCode = int32(ee.ExitCode())
		status = pb.ResultStatus_RESULT_FAIL
	} else {
		exitCode = -1
		status = pb.ResultStatus_RESULT_FAIL
		completed.Error = runErr.Error()
	}
	completed.ExitCode = int(exitCode)
	if req.Sink != nil {
		req.Sink.Record(completed)
	}
	return
}
