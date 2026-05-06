// Package executor runs shell commands from ServerToAgent commands.
package executor

import (
	"bytes"
	"context"
	"os/exec"
	"time"

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
