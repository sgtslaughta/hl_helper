// Package terminal implements PTY shell sessions for the hl-agent.
//
// A Session bridges a remote control plane (typically gRPC) to a local PTY,
// recording the stream as asciicast v2 for replay.
package terminal

import "time"

// FrameType enumerates the frame kinds.
type FrameType string

const (
	FrameStdin  FrameType = "stdin"
	FrameStdout FrameType = "stdout"
	FrameResize FrameType = "resize"
	FrameKill   FrameType = "kill"
)

// Frame is the wire-level message.
type Frame struct {
	Type FrameType `json:"type"`
	Data []byte    `json:"data,omitempty"`
	Cols int       `json:"cols,omitempty"`
	Rows int       `json:"rows,omitempty"`
}

// SessionConfig configures a new shell session.
type SessionConfig struct {
	Shell     string        // default /bin/bash
	User      string        // run-as user; empty = current
	Cwd       string        // working dir; empty = $HOME
	Cols      int           // initial cols (default 80)
	Rows      int           // initial rows (default 24)
	AllowList []string      // command regex allowlist (advisory)
	Idle      time.Duration // kill after no I/O
	RecordTo  string        // asciicast output path; empty = no recording
}

func (c *SessionConfig) defaults() {
	if c.Shell == "" {
		c.Shell = "/bin/bash"
	}
	if c.Cols == 0 {
		c.Cols = 80
	}
	if c.Rows == 0 {
		c.Rows = 24
	}
}
