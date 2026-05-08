package exec_test

import (
	"context"
	"runtime"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/exec"
	"go.uber.org/goleak"
)

func TestMain(m *testing.M) {
	goleak.VerifyTestMain(m)
}

func TestAllowlistRejectsUnknownBinary(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/echo",
		AllowAnyArgs: true,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	result := runner.Run(context.Background(), "/bin/cat", []string{}, out)

	if result.Err != exec.ErrBinaryNotAllowed {
		t.Fatalf("expected ErrBinaryNotAllowed, got %v", result.Err)
	}
}

func TestAllowlistRejectsDisallowedArg(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/echo",
		AllowedArgs: []string{"hello"},
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	result := runner.Run(context.Background(), "/bin/echo", []string{"world"}, out)

	if result.Err != exec.ErrArgNotAllowed {
		t.Fatalf("expected ErrArgNotAllowed, got %v", result.Err)
	}
}

func TestAllowAnyArgsBypassesArgCheck(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/echo",
		AllowAnyArgs: true,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	result := runner.Run(context.Background(), "/bin/echo", []string{"arbitrary", "args"}, out)

	if result.Err != nil {
		t.Fatalf("expected no error, got %v", result.Err)
	}
	// runner closes out
}

func TestRunStreamsStdout(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/echo",
		AllowAnyArgs: true,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	result := runner.Run(context.Background(), "/bin/echo", []string{"hello"}, out)

	if result.Err != nil {
		t.Fatalf("expected no error, got %v", result.Err)
	}

	var stdoutData string
	for chunk := range out {
		if chunk.Stream == "stdout" {
			stdoutData += string(chunk.Data)
		}
	}

	if stdoutData != "hello\n" {
		t.Fatalf("expected stdout 'hello\\n', got %q", stdoutData)
	}
	if result.ExitCode != 0 {
		t.Fatalf("expected exit code 0, got %d", result.ExitCode)
	}
}

func TestRunCapturesNonZeroExitCode(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/sh",
		AllowAnyArgs: true,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	result := runner.Run(context.Background(), "/bin/sh", []string{"-c", "exit 7"}, out)

	// drain channel
	for range out {
	}

	if result.ExitCode != 7 {
		t.Fatalf("expected exit code 7, got %d", result.ExitCode)
	}
	if result.Err == nil {
		t.Fatalf("expected error for non-zero exit, got nil")
	}
}

func TestRunHonorsContextCancel(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/sleep",
		AllowAnyArgs: true,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	ctx, cancel := context.WithCancel(context.Background())
	out := make(chan exec.Chunk, 100)

	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel()
	}()

	start := time.Now()
	result := runner.Run(ctx, "/bin/sleep", []string{"30"}, out)
	elapsed := time.Since(start)

	if elapsed > 5*time.Second {
		t.Fatalf("expected quick cancellation, took %v", elapsed)
	}

	if result.Err == nil {
		t.Fatalf("expected error on cancel, got nil")
	}

	// drain channel
	for range out {
	}
}

func TestRunHonorsTimeout(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/sleep",
		AllowAnyArgs: true,
		Timeout:     200 * time.Millisecond,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	start := time.Now()
	result := runner.Run(context.Background(), "/bin/sleep", []string{"5"}, out)
	elapsed := time.Since(start)

	if elapsed > 5*time.Second {
		t.Fatalf("expected timeout, took %v", elapsed)
	}

	if result.Err != exec.ErrTimeout {
		t.Fatalf("expected ErrTimeout, got %v", result.Err)
	}

	// drain channel
	for range out {
	}
}

func TestRunChunkChannelClosesOnExit(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/echo",
		AllowAnyArgs: true,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	result := runner.Run(context.Background(), "/bin/echo", []string{"test"}, out)

	if result.Err != nil {
		t.Fatalf("expected no error, got %v", result.Err)
	}

	// verify channel closes
	timeout := time.NewTimer(1 * time.Second)
	defer timeout.Stop()

	select {
	case _, ok := <-out:
		if ok {
			// drain rest
			for range out {
			}
		}
	case <-timeout.C:
		t.Fatalf("timeout waiting for channel close")
	}
}

func TestStderrChunksRoutedSeparately(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	rule := exec.AllowRule{
		Binary:      "/bin/sh",
		AllowAnyArgs: true,
	}
	allow := exec.NewAllowlist(rule)
	runner := exec.NewRunner(allow, exec.Elevator{Kind: exec.ElevatorDirect})

	out := make(chan exec.Chunk, 100)
	result := runner.Run(context.Background(), "/bin/sh", []string{"-c", "echo a; echo b 1>&2"}, out)

	if result.Err != nil {
		t.Fatalf("expected no error, got %v", result.Err)
	}

	var stdout, stderr string
	for chunk := range out {
		if chunk.Stream == "stdout" {
			stdout += string(chunk.Data)
		} else if chunk.Stream == "stderr" {
			stderr += string(chunk.Data)
		}
	}

	if stdout != "a\n" {
		t.Fatalf("expected stdout 'a\\n', got %q", stdout)
	}
	if stderr != "b\n" {
		t.Fatalf("expected stderr 'b\\n', got %q", stderr)
	}
}
