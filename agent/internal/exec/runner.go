// Package exec runs allowlisted external programs and streams their output.
package exec

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os/exec"
	"sync"
	"time"
)

var (
	ErrBinaryNotAllowed = errors.New("exec: binary not in allowlist")
	ErrArgNotAllowed    = errors.New("exec: argument not in allowlist")
	ErrTimeout          = errors.New("exec: timeout")
)

// AllowRule describes one permitted invocation.
type AllowRule struct {
	Binary       string        // absolute path, e.g. "/usr/bin/apt-get"
	AllowedArgs  []string      // exact-match allowlist (e.g. "update", "upgrade", "-y")
	AllowAnyArgs bool          // for tools where args are dynamic (e.g. "uname -a")
	AsRoot       bool          // run via sudo (uses agent's sudoers fragment)
	Timeout      time.Duration
}

// Allowlist holds rules keyed by binary path.
type Allowlist struct {
	rules map[string]AllowRule
	mu    sync.RWMutex
}

// NewAllowlist creates an Allowlist from rules.
func NewAllowlist(rules ...AllowRule) *Allowlist {
	a := &Allowlist{
		rules: make(map[string]AllowRule),
	}
	for _, rule := range rules {
		a.rules[rule.Binary] = rule
	}
	return a
}

// Check returns nil if (binary, args) is permitted; else error.
func (a *Allowlist) Check(binary string, args []string) error {
	a.mu.RLock()
	defer a.mu.RUnlock()

	rule, ok := a.rules[binary]
	if !ok {
		return ErrBinaryNotAllowed
	}

	if rule.AllowAnyArgs {
		return nil
	}

	// Check each arg is in allowlist
	for _, arg := range args {
		found := false
		for _, allowed := range rule.AllowedArgs {
			if arg == allowed {
				found = true
				break
			}
		}
		if !found {
			return ErrArgNotAllowed
		}
	}

	return nil
}

// Chunk is one stream output piece.
type Chunk struct {
	Stream string // "stdout" or "stderr"
	Data   []byte
}

// Result captures the final outcome.
type Result struct {
	ExitCode int
	Err      error // non-nil for non-zero exit OR runner errors
}

// Runner executes commands per Allowlist, streaming output via channel.
type Runner struct {
	allow *Allowlist
}

// NewRunner creates a new Runner with an Allowlist.
func NewRunner(allow *Allowlist) *Runner {
	return &Runner{allow: allow}
}

// Run executes binary with args, sending output chunks on out (closed when done).
// Honors ctx cancel + per-rule timeout. AsRoot rules prepend "sudo --non-interactive".
// Returns the Result.
func (r *Runner) Run(ctx context.Context, binary string, args []string, out chan<- Chunk) Result {
	// Check allowlist
	if err := r.allow.Check(binary, args); err != nil {
		return Result{Err: err}
	}

	// Get the rule to check for timeout and AsRoot
	r.allow.mu.RLock()
	rule := r.allow.rules[binary]
	r.allow.mu.RUnlock()

	// Apply per-rule timeout if set
	if rule.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, rule.Timeout)
		defer cancel()
	}

	// Build command
	var cmdBinary string
	var cmdArgs []string

	if rule.AsRoot {
		cmdBinary = "sudo"
		cmdArgs = append([]string{"--non-interactive", "--"}, binary)
		cmdArgs = append(cmdArgs, args...)
	} else {
		cmdBinary = binary
		cmdArgs = args
	}

	cmd := exec.CommandContext(ctx, cmdBinary, cmdArgs...)

	// Set up pipes for stdout and stderr
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return Result{Err: err}
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return Result{Err: err}
	}

	// Start command
	if err := cmd.Start(); err != nil {
		return Result{Err: err}
	}

	// Read output in separate goroutines
	var wg sync.WaitGroup
	wg.Add(2)

	go readStream(&wg, stdout, "stdout", out)
	go readStream(&wg, stderr, "stderr", out)

	// Drain pipes before cmd.Wait() to avoid race where Wait closes the parent
	// end of the pipe while a reader goroutine is mid-read (yields ErrClosed
	// or lost data). Goroutines exit on EOF after child process closes its
	// end, which happens before cmd.Wait() returns.
	wg.Wait()
	cmdErr := cmd.Wait()
	close(out)

	// Determine exit code and error
	var exitCode int
	if cmdErr != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return Result{ExitCode: -1, Err: ErrTimeout}
		}
		var exitErr *exec.ExitError
		if errors.As(cmdErr, &exitErr) {
			exitCode = exitErr.ExitCode()
		} else {
			return Result{ExitCode: -1, Err: cmdErr}
		}
	} else {
		exitCode = 0
	}

	// Return result with error if non-zero exit
	var resultErr error
	if exitCode != 0 {
		resultErr = fmt.Errorf("exec: exit code %d", exitCode)
	}
	return Result{ExitCode: exitCode, Err: resultErr}
}

// readStream reads from a pipe in 64KB chunks and sends them on out.
func readStream(wg *sync.WaitGroup, r io.Reader, streamName string, out chan<- Chunk) {
	defer wg.Done()

	reader := bufio.NewReaderSize(r, 64*1024)
	for {
		data := make([]byte, 64*1024)
		n, err := reader.Read(data)
		if n > 0 {
			out <- Chunk{Stream: streamName, Data: data[:n]}
		}
		if err != nil {
			// Suppress io.EOF and pipe-closed-after-Wait noise (race with cmd.Wait
			// closing pipes before goroutine drains EOF).
			if err != io.EOF && !errors.Is(err, fs.ErrClosed) {
				out <- Chunk{Stream: streamName, Data: []byte(fmt.Sprintf("error: %v", err))}
			}
			break
		}
	}
}
