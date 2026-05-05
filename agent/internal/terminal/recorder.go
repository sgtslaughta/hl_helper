package terminal

import (
	"encoding/json"
	"fmt"
	"io"
	"sync"
	"time"
)

// Recorder writes an asciicast v2 stream.
//
// Format:
//
//	{"version":2,"width":W,"height":H,"timestamp":TS,"env":{...}}
//	[elapsed, "o", "data"]
//	[elapsed, "i", "data"]
type Recorder struct {
	w     io.Writer
	start time.Time
	mu    sync.Mutex
}

// NewRecorder writes the v2 header to w and returns a Recorder.
func NewRecorder(w io.Writer, cols, rows int) (*Recorder, error) {
	header := map[string]any{
		"version":   2,
		"width":     cols,
		"height":    rows,
		"timestamp": time.Now().Unix(),
		"env":       map[string]string{"SHELL": "/bin/bash", "TERM": "xterm-256color"},
	}
	b, err := json.Marshal(header)
	if err != nil {
		return nil, err
	}
	if _, err := fmt.Fprintf(w, "%s\n", b); err != nil {
		return nil, err
	}
	return &Recorder{w: w, start: time.Now()}, nil
}

// Write records a frame of stdout ("o") or stdin ("i").
func (r *Recorder) Write(kind string, data []byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	elapsed := time.Since(r.start).Seconds()
	row := []any{elapsed, kind, string(data)}
	b, err := json.Marshal(row)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(r.w, "%s\n", b)
	return err
}

// Close is a no-op for the v2 stream (no footer).
func (r *Recorder) Close() error { return nil }
