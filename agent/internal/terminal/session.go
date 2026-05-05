package terminal

import (
	"context"
	"fmt"
	"io"
	"os"
	"sync"
)

// Session ties a PTY to bidirectional frame channels and an optional recorder.
type Session struct {
	pty      PTY
	recorder *Recorder
	stdin    chan Frame
	stdout   chan Frame
	done     chan struct{}
	once     sync.Once
}

// NewSession spawns the shell and starts read/write goroutines.
func NewSession(cfg SessionConfig) (*Session, error) {
	cfg.defaults()
	pty, err := Spawn(cfg)
	if err != nil {
		return nil, err
	}
	s := &Session{
		pty:    pty,
		stdin:  make(chan Frame, 16),
		stdout: make(chan Frame, 64),
		done:   make(chan struct{}),
	}
	if cfg.RecordTo != "" {
		f, err := os.Create(cfg.RecordTo)
		if err != nil {
			_ = pty.Close()
			return nil, fmt.Errorf("recorder: %w", err)
		}
		rec, err := NewRecorder(f, cfg.Cols, cfg.Rows)
		if err != nil {
			_ = pty.Close()
			_ = f.Close()
			return nil, err
		}
		s.recorder = rec
	}
	go s.readLoop()
	go s.writeLoop()
	return s, nil
}

// Stdin returns the channel callers send Frame{Type:stdin} on.
func (s *Session) Stdin() chan<- Frame { return s.stdin }

// Stdout returns the channel callers receive Frame{Type:stdout} from.
func (s *Session) Stdout() <-chan Frame { return s.stdout }

// Done closes when the session terminates.
func (s *Session) Done() <-chan struct{} { return s.done }

// Resize changes the PTY window size.
func (s *Session) Resize(cols, rows int) error { return s.pty.Resize(cols, rows) }

// Kill terminates the session immediately.
func (s *Session) Kill(_ context.Context) {
	s.once.Do(func() {
		_ = s.pty.Close()
		close(s.done)
	})
}

func (s *Session) readLoop() {
	defer s.Kill(context.Background())
	buf := make([]byte, 4096)
	for {
		n, err := s.pty.Read(buf)
		if n > 0 {
			data := append([]byte(nil), buf[:n]...)
			if s.recorder != nil {
				_ = s.recorder.Write("o", data)
			}
			select {
			case s.stdout <- Frame{Type: FrameStdout, Data: data}:
			case <-s.done:
				return
			}
		}
		if err != nil {
			if err == io.EOF {
				return
			}
			return
		}
	}
}

func (s *Session) writeLoop() {
	for {
		select {
		case <-s.done:
			return
		case f := <-s.stdin:
			switch f.Type {
			case FrameStdin:
				if s.recorder != nil {
					_ = s.recorder.Write("i", f.Data)
				}
				_, _ = s.pty.Write(f.Data)
			case FrameResize:
				_ = s.pty.Resize(f.Cols, f.Rows)
			case FrameKill:
				s.Kill(context.Background())
				return
			}
		}
	}
}
