package logtypes

import (
	"errors"
	"time"
)

// Level is an ordered log severity.
type Level int

const (
	LevelDebug    Level = 10
	LevelInfo     Level = 20
	LevelWarn     Level = 30
	LevelError    Level = 40
	LevelCritical Level = 50
)

// ParseLevel converts a wire-format level string into a Level.
func ParseLevel(s string) (Level, error) {
	switch s {
	case "debug":
		return LevelDebug, nil
	case "info":
		return LevelInfo, nil
	case "warn":
		return LevelWarn, nil
	case "error":
		return LevelError, nil
	case "critical":
		return LevelCritical, nil
	}
	return 0, errors.New("unknown level: " + s)
}

// LevelString is the inverse of ParseLevel.
func LevelString(l Level) string {
	switch l {
	case LevelDebug:
		return "debug"
	case LevelInfo:
		return "info"
	case LevelWarn:
		return "warn"
	case LevelError:
		return "error"
	case LevelCritical:
		return "critical"
	}
	return "info"
}

type Outcome int

const (
	OutcomeUnknown Outcome = 0
	OutcomeSuccess Outcome = 1
	OutcomeFailure Outcome = 2
)

// Event is the ECS-aligned activity event emitted by the agent.
type Event struct {
	TS         time.Time         `json:"@timestamp"`
	ECSVersion string            `json:"ecs.version"`
	Event      EventFields       `json:"event"`
	Agent      AgentFields       `json:"agent"`
	Host       HostFields        `json:"host"`
	Log        LogFields         `json:"log"`
	Labels     map[string]string `json:"labels,omitempty"`
	Message    string            `json:"message,omitempty"`
	Error      *ErrorFields      `json:"error,omitempty"`
	Details    map[string]any    `json:"details,omitempty"`
}

type EventFields struct {
	Kind     string   `json:"kind"`
	Category []string `json:"category"`
	Type     []string `json:"type,omitempty"`
	Action   string   `json:"action"`
	Outcome  string   `json:"outcome,omitempty"`
	Duration int64    `json:"duration,omitempty"`
	Sequence uint64   `json:"sequence"`
	ID       string   `json:"id"`
}

type AgentFields struct {
	ID        string `json:"id"`
	Version   string `json:"version,omitempty"`
	Type      string `json:"type"`
	SessionID string `json:"session_id"`
}

type HostFields struct {
	ID   string `json:"id"`
	Name string `json:"name,omitempty"`
}

type LogFields struct {
	Level  string `json:"level"`
	Logger string `json:"logger,omitempty"`
}

type ErrorFields struct {
	Code       string `json:"code,omitempty"`
	Message    string `json:"message,omitempty"`
	StackTrace string `json:"stack_trace,omitempty"`
}
