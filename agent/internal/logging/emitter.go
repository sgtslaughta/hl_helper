package logging

import (
	"fmt"
	"os"
	"sync/atomic"
	"time"

	"github.com/oklog/ulid/v2"

	"github.com/hlhelper/hl-agent/internal/logging/buffer"
	"github.com/hlhelper/hl-agent/internal/logtypes"
)

type Config struct {
	BufferPath   string
	AgentID      string
	SessionID    string
	HostID       string
	HostName     string
	AgentVer     string
	FallbackFile string
	MaxBytes     int64
	MaxAge       time.Duration
}

type Emitter struct {
	cfg      Config
	buf      *buffer.Buffer
	seq      uint64
	fallback *os.File
}

func New(cfg Config) (*Emitter, error) {
	if cfg.MaxBytes == 0 {
		cfg.MaxBytes = 50 * 1024 * 1024
	}
	if cfg.MaxAge == 0 {
		cfg.MaxAge = 7 * 24 * time.Hour
	}
	if cfg.FallbackFile == "" {
		cfg.FallbackFile = "/var/log/hl-agent/fallback.log"
	}
	b, err := buffer.Open(cfg.BufferPath, buffer.Options{MaxBytes: cfg.MaxBytes, MaxAge: cfg.MaxAge})
	if err != nil {
		return nil, err
	}
	fb, _ := os.OpenFile(cfg.FallbackFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600) // best-effort
	return &Emitter{cfg: cfg, buf: b, fallback: fb}, nil
}

func (e *Emitter) Close() error {
	if e.fallback != nil {
		_ = e.fallback.Close()
	}
	return e.buf.Close()
}

func (e *Emitter) Buffer() *buffer.Buffer {
	return e.buf
}

func (e *Emitter) PendingCount() int {
	return e.buf.Count()
}

// Emit records a successful event. Implements EventEmitter.
func (e *Emitter) Emit(level logtypes.Level, category, action, message string, details map[string]any) {
	e.emit(level, category, action, message, details, nil)
}

// EmitErr records a failure event with error details. Implements EventEmitter.
func (e *Emitter) EmitErr(level logtypes.Level, category, action, message, errCode, errMessage string, details map[string]any) {
	e.emit(level, category, action, message, details, &logtypes.ErrorFields{Code: errCode, Message: errMessage})
}

func (e *Emitter) emit(level logtypes.Level, category, action, message string, details map[string]any, ef *logtypes.ErrorFields) {
	defer func() {
		if r := recover(); r != nil && e.fallback != nil {
			_, _ = fmt.Fprintf(e.fallback, "[logger-panic] %v\n", r)
		}
	}()
	seq := atomic.AddUint64(&e.seq, 1)
	ev := logtypes.Event{
		TS:         time.Now().UTC(),
		ECSVersion: "8.11",
		Event: logtypes.EventFields{
			Kind:     "event",
			Category: []string{category},
			Action:   action,
			Sequence: seq,
			ID:       ulid.Make().String(),
		},
		Agent: logtypes.AgentFields{ID: e.cfg.AgentID, Version: e.cfg.AgentVer, Type: "hl-agent", SessionID: e.cfg.SessionID},
		Host:  logtypes.HostFields{ID: e.cfg.HostID, Name: e.cfg.HostName},
		Log:   logtypes.LogFields{Level: logtypes.LevelString(level)},
		Message: message,
		Details: details,
	}
	if ef != nil {
		ev.Event.Outcome = "failure"
		ev.Error = ef
	} else if action != "" {
		// default outcome to success unless caller signals otherwise
		ev.Event.Outcome = "success"
	}
	if err := e.buf.Append(ev); err != nil && e.fallback != nil {
		_, _ = fmt.Fprintf(e.fallback, "[logger-buf-err] action=%s seq=%d err=%v\n", action, seq, err)
	}
}
