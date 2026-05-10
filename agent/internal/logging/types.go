package logging

import (
	"github.com/hlhelper/hl-agent/internal/logtypes"
)

// Re-export types from logtypes for backward compatibility and clean API
type Level = logtypes.Level

const (
	LevelDebug    = logtypes.LevelDebug
	LevelInfo     = logtypes.LevelInfo
	LevelWarn     = logtypes.LevelWarn
	LevelError    = logtypes.LevelError
	LevelCritical = logtypes.LevelCritical
)

// ParseLevel converts a wire-format level string into a Level.
func ParseLevel(s string) (Level, error) {
	return logtypes.ParseLevel(s)
}

// LevelString is the inverse of ParseLevel.
func LevelString(l Level) string {
	return logtypes.LevelString(l)
}

type Outcome = logtypes.Outcome

const (
	OutcomeUnknown = logtypes.OutcomeUnknown
	OutcomeSuccess = logtypes.OutcomeSuccess
	OutcomeFailure = logtypes.OutcomeFailure
)

// Event is the ECS-aligned activity event emitted by the agent.
type Event = logtypes.Event
type EventFields = logtypes.EventFields
type AgentFields = logtypes.AgentFields
type HostFields = logtypes.HostFields
type LogFields = logtypes.LogFields
type ErrorFields = logtypes.ErrorFields
