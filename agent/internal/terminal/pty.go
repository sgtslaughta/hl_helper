package terminal

import (
	"fmt"
	"io"
	"os"
	"os/exec"

	"github.com/creack/pty"
)

// PTY is the abstract handle returned by Spawn.
type PTY interface {
	io.ReadWriteCloser
	Resize(cols, rows int) error
	Wait() error
}

// realPTY wraps an *os.File from creack/pty plus the underlying *exec.Cmd.
type realPTY struct {
	f   *os.File
	cmd *exec.Cmd
}

func (r *realPTY) Read(p []byte) (int, error)  { return r.f.Read(p) }
func (r *realPTY) Write(p []byte) (int, error) { return r.f.Write(p) }
func (r *realPTY) Close() error {
	_ = r.f.Close()
	if r.cmd.Process != nil {
		_ = r.cmd.Process.Kill()
	}
	return nil
}
func (r *realPTY) Resize(cols, rows int) error {
	return pty.Setsize(r.f, &pty.Winsize{Cols: uint16(cols), Rows: uint16(rows)})
}
func (r *realPTY) Wait() error { return r.cmd.Wait() }

// Spawn launches the configured shell behind a PTY.
//
// The environment is scrubbed to a minimal allowlist (TERM, PATH, HOME, USER).
func Spawn(cfg SessionConfig) (PTY, error) {
	cfg.defaults()
	cmd := exec.Command(cfg.Shell, "-l")
	if cfg.Cwd != "" {
		cmd.Dir = cfg.Cwd
	}
	cmd.Env = scrubEnv()
	f, err := pty.StartWithSize(cmd, &pty.Winsize{Cols: uint16(cfg.Cols), Rows: uint16(cfg.Rows)})
	if err != nil {
		return nil, fmt.Errorf("pty start: %w", err)
	}
	return &realPTY{f: f, cmd: cmd}, nil
}

func scrubEnv() []string {
	keep := []string{"TERM", "PATH", "HOME", "USER", "LANG", "LC_ALL"}
	var out []string
	for _, k := range keep {
		if v := os.Getenv(k); v != "" {
			out = append(out, k+"="+v)
		}
	}
	return out
}
