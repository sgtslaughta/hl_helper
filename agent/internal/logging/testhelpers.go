package logging

import (
	"github.com/hlhelper/hl-agent/internal/logtypes"
)

// EventEmitter is an interface satisfied by *Emitter and test fakes.
// Subsystems should depend on this interface, not the concrete Emitter.
type EventEmitter interface {
	Emit(level logtypes.Level, category, action, message string, details map[string]any)
	EmitErr(level logtypes.Level, category, action, message, errCode, errMessage string, details map[string]any)
}

// FakeEmitter records emitted events for testing.
// Implements EventEmitter.
type FakeEmitter struct {
	Events []FakeEvent
}

// FakeEvent represents a recorded event.
type FakeEvent struct {
	Level       logtypes.Level
	Category    string
	Action      string
	Message     string
	Details     map[string]any
	ErrorCode   string
	ErrorMsg    string
	IsError     bool
}

// Emit appends a success event to the FakeEmitter's event list.
func (f *FakeEmitter) Emit(level logtypes.Level, category, action, message string, details map[string]any) {
	f.Events = append(f.Events, FakeEvent{
		Level:    level,
		Category: category,
		Action:   action,
		Message:  message,
		Details:  details,
		IsError:  false,
	})
}

// EmitErr appends an error event to the FakeEmitter's event list.
func (f *FakeEmitter) EmitErr(level logtypes.Level, category, action, message, errCode, errMessage string, details map[string]any) {
	f.Events = append(f.Events, FakeEvent{
		Level:     level,
		Category:  category,
		Action:    action,
		Message:   message,
		Details:   details,
		ErrorCode: errCode,
		ErrorMsg:  errMessage,
		IsError:   true,
	})
}
