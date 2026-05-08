package executor

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// AuditPhase identifies a point in an elevated command lifecycle.
type AuditPhase string

const (
	PhaseStarted   AuditPhase = "started"
	PhaseCompleted AuditPhase = "completed"
	PhaseDenied    AuditPhase = "denied"
)

// ElevatedEvent describes one moment in the lifecycle of an elevated exec.
type ElevatedEvent struct {
	Timestamp time.Time  `json:"timestamp"`
	TaskID    string     `json:"task_id"`
	Binary    string     `json:"binary"`
	Args      []string   `json:"args"`
	Elevator  string     `json:"elevator"`
	Reason    string     `json:"reason"`
	Phase     AuditPhase `json:"phase"`
	ExitCode  int        `json:"exit_code,omitempty"`
	Error     string     `json:"error,omitempty"`
}

// AuditSink records elevated events. Implementations must be safe for concurrent use.
type AuditSink interface {
	Record(ev ElevatedEvent)
}

// MultiSink fans Record out to N sinks.
type MultiSink struct{ sinks []AuditSink }

func NewMultiSink(sinks ...AuditSink) *MultiSink { return &MultiSink{sinks: sinks} }

func (m *MultiSink) Record(ev ElevatedEvent) {
	for _, s := range m.sinks {
		s.Record(ev)
	}
}

// JSONLSink appends events to a JSONL file. Rotates by renaming current to `.1`
// when size exceeds maxBytes. Best-effort: write errors are silently dropped
// (audit is not allowed to break exec).
type JSONLSink struct {
	mu       sync.Mutex
	path     string
	maxBytes int64
}

// NewJSONLSink creates a JSONL sink at path, rotating at maxBytes.
// Parent directory is created on first write (mode 0750).
func NewJSONLSink(path string, maxBytes int64) *JSONLSink {
	return &JSONLSink{path: path, maxBytes: maxBytes}
}

func (j *JSONLSink) Record(ev ElevatedEvent) {
	j.mu.Lock()
	defer j.mu.Unlock()

	if err := os.MkdirAll(filepath.Dir(j.path), 0o750); err != nil {
		return
	}

	if fi, err := os.Stat(j.path); err == nil && fi.Size() >= j.maxBytes {
		_ = os.Rename(j.path, j.path+".1")
	}

	f, err := os.OpenFile(j.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o640)
	if err != nil {
		return
	}
	defer f.Close()

	line, err := json.Marshal(ev)
	if err != nil {
		return
	}
	_, _ = f.Write(append(line, '\n'))
}
