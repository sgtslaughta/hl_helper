// Package power implements local reboot/shutdown executors for hl-agent.
//
// All operations gate on a Confirm flag to avoid accidental invocation from
// dispatched commands. The control plane must explicitly set Confirm=true.
package power

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strconv"
	"time"
)

// ErrNotConfirmed signals an unconfirmed power op.
var ErrNotConfirmed = errors.New("power: confirm flag not set")

// Op enumerates the supported power ops.
type Op string

const (
	OpReboot   Op = "reboot"
	OpShutdown Op = "shutdown"
)

// Request specifies a reboot/shutdown invocation.
type Request struct {
	Op      Op
	Delay   time.Duration // 0 = immediate
	Reason  string        // recorded in wall message
	Confirm bool
}

// Result is returned after dispatching to the system shutdown binary.
type Result struct {
	Op       Op
	Issued   time.Time
	Command  string
	Output   []byte
	Deferred bool // true when Delay > 0
}

// Runner abstracts process execution for tests.
type Runner interface {
	Run(ctx context.Context, name string, args ...string) ([]byte, error)
}

// ExecRunner is the default Runner.
type ExecRunner struct{}

// Run executes name with args.
func (ExecRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	if err := cmd.Run(); err != nil {
		return buf.Bytes(), err
	}
	return buf.Bytes(), nil
}

// Manager wires a Runner. Use New() for production.
type Manager struct {
	R Runner
}

// New returns a Manager backed by the OS shutdown binary.
func New() *Manager { return &Manager{R: ExecRunner{}} }

// Apply executes the request. Returns ErrNotConfirmed when Confirm is false.
func (m *Manager) Apply(ctx context.Context, req Request) (*Result, error) {
	if !req.Confirm {
		return nil, ErrNotConfirmed
	}
	switch req.Op {
	case OpReboot, OpShutdown:
	default:
		return nil, fmt.Errorf("power: unknown op %q", req.Op)
	}

	delayArg := "now"
	if req.Delay > 0 {
		// shutdown(8) accepts +<minutes>
		minutes := int(req.Delay.Minutes())
		if minutes < 1 {
			minutes = 1
		}
		delayArg = "+" + strconv.Itoa(minutes)
	}

	flag := "-r"
	if req.Op == OpShutdown {
		flag = "-h"
	}
	args := []string{flag, delayArg}
	if req.Reason != "" {
		args = append(args, "hl_helper: "+req.Reason)
	}

	out, err := m.R.Run(ctx, "shutdown", args...)
	res := &Result{
		Op:       req.Op,
		Issued:   time.Now().UTC(),
		Command:  "shutdown " + joinArgs(args),
		Output:   out,
		Deferred: req.Delay > 0,
	}
	if err != nil {
		return res, fmt.Errorf("shutdown failed: %w: %s", err, string(out))
	}
	return res, nil
}

// Cancel calls `shutdown -c` to abort a previously-scheduled deferred op.
func (m *Manager) Cancel(ctx context.Context) error {
	if _, err := m.R.Run(ctx, "shutdown", "-c"); err != nil {
		return fmt.Errorf("shutdown -c: %w", err)
	}
	return nil
}

func joinArgs(args []string) string {
	out := ""
	for i, a := range args {
		if i > 0 {
			out += " "
		}
		out += a
	}
	return out
}
