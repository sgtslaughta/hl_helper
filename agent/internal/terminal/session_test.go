package terminal

import (
	"errors"
	"io"
	"sync"
	"testing"
)

// fakePTY is a controllable PTY for tests. Reads return queued bytes; Writes
// are captured. Closing returns io.EOF on next Read.
type fakePTY struct {
	mu       sync.Mutex
	readQ    [][]byte
	written  []byte
	closed   bool
	resizeCh chan [2]int
}

func newFakePTY() *fakePTY { return &fakePTY{resizeCh: make(chan [2]int, 4)} }

func (f *fakePTY) Read(p []byte) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.closed {
		return 0, io.EOF
	}
	if len(f.readQ) == 0 {
		return 0, io.EOF
	}
	n := copy(p, f.readQ[0])
	f.readQ = f.readQ[1:]
	return n, nil
}
func (f *fakePTY) Write(p []byte) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.closed {
		return 0, errors.New("closed")
	}
	f.written = append(f.written, p...)
	return len(p), nil
}
func (f *fakePTY) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.closed = true
	return nil
}
func (f *fakePTY) Resize(c, r int) error {
	select {
	case f.resizeCh <- [2]int{c, r}:
	default:
	}
	return nil
}
func (f *fakePTY) Wait() error { return nil }

func TestSessionStdoutForward(t *testing.T) {
	f := newFakePTY()
	f.readQ = [][]byte{[]byte("hello")}
	s := &Session{
		pty:    f,
		stdin:  make(chan Frame, 4),
		stdout: make(chan Frame, 4),
		done:   make(chan struct{}),
	}
	go s.readLoop()
	got := <-s.stdout
	if string(got.Data) != "hello" {
		t.Fatalf("got %q", got.Data)
	}
	<-s.Done()
}

func TestSessionStdinAndKill(t *testing.T) {
	f := newFakePTY()
	s := &Session{
		pty:    f,
		stdin:  make(chan Frame, 4),
		stdout: make(chan Frame, 4),
		done:   make(chan struct{}),
	}
	go s.writeLoop()
	s.stdin <- Frame{Type: FrameStdin, Data: []byte("ls\n")}
	s.stdin <- Frame{Type: FrameKill}
	<-s.Done()
	if string(f.written) != "ls\n" {
		t.Fatalf("got %q", f.written)
	}
}
