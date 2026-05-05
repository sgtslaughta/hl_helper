// Package providers defines the package manager provider interface used by
// the hl-agent update engine. Concrete providers (apt, dnf, apk) live in
// subpackages and share this contract.
package providers

import (
	"bytes"
	"context"
	"errors"
	"os/exec"
)

// ErrNotSupported signals an operation a provider cannot perform (e.g. apk rollback).
var ErrNotSupported = errors.New("operation not supported by this provider")

// Package describes an installed package.
type Package struct {
	Name    string
	Version string
	Arch    string
}

// Update describes a pending upgrade for a single package.
type Update struct {
	Name     string
	From     string
	To       string
	Security bool
}

// ApplyOpts tunes Apply behavior.
type ApplyOpts struct {
	DryRun  bool
	Timeout int // seconds; 0 = no override
}

// ApplyResult is returned from Apply.
type ApplyResult struct {
	TxID    string
	Updated []string
	Failed  []string
}

// Provider is the contract every package manager wrapper implements.
type Provider interface {
	Name() string
	Detect(ctx context.Context) (bool, error)
	List(ctx context.Context) ([]Package, error)
	CheckUpdates(ctx context.Context) ([]Update, error)
	Apply(ctx context.Context, pkgs []string, opts ApplyOpts) (*ApplyResult, error)
	Rollback(ctx context.Context, txID string) error
}

// Runner abstracts process execution so tests can inject canned responses
// without touching real package managers.
type Runner interface {
	Run(ctx context.Context, env map[string]string, name string, args ...string) ([]byte, error)
}

// ExecRunner is the production Runner backed by os/exec.
type ExecRunner struct{}

// Run executes name with args and merged env, returning combined output.
func (ExecRunner) Run(ctx context.Context, env map[string]string, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	if len(env) > 0 {
		cmd.Env = append(cmd.Environ(), envSlice(env)...)
	}
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	if err := cmd.Run(); err != nil {
		return buf.Bytes(), err
	}
	return buf.Bytes(), nil
}

func envSlice(m map[string]string) []string {
	out := make([]string, 0, len(m))
	for k, v := range m {
		out = append(out, k+"="+v)
	}
	return out
}
