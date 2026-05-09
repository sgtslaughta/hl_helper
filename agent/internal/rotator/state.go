// Package rotator manages TLS cert rotation lifecycle for the agent.
package rotator

import (
	"encoding/json"
	"errors"
	"fmt"
	"math/rand"
	"os"
	"time"
)

type Phase string

const (
	StateNormal        Phase = "NORMAL"
	StateRotating      Phase = "ROTATING"
	StateRotateBackoff Phase = "ROTATE_BACKOFF"
	StateRecovering    Phase = "RECOVERING"
	StateHalted        Phase = "HALTED"
)

type State struct {
	Phase               Phase     `json:"phase"`
	LastAttemptAt       time.Time `json:"last_attempt_at,omitempty"`
	ConsecutiveFailures int       `json:"consecutive_failures"`
	HaltedReason        string    `json:"halted_reason,omitempty"`
}

func LoadState(path string) (State, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return State{Phase: StateNormal}, nil
	}
	if err != nil {
		return State{}, fmt.Errorf("read state: %w", err)
	}
	var s State
	if err := json.Unmarshal(data, &s); err != nil {
		return State{}, fmt.Errorf("decode state: %w", err)
	}
	if s.Phase == "" {
		s.Phase = StateNormal
	}
	return s, nil
}

func SaveState(path string, s State) error {
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return fmt.Errorf("encode state: %w", err)
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return fmt.Errorf("write tmp: %w", err)
	}
	return os.Rename(tmp, path)
}

// ComputeRotateAfter returns the absolute time at which rotation should be
// attempted. Default: 50% of (notBefore..notAfter) elapsed, with optional
// jitter as a fraction (e.g. 0.10 = ±10%) applied to the half-life.
func ComputeRotateAfter(notBefore, notAfter, now time.Time, jitterFrac float64) time.Time {
	span := notAfter.Sub(notBefore)
	half := span / 2
	if jitterFrac > 0 {
		// Jitter in range [-jitterFrac*half, +jitterFrac*half].
		delta := time.Duration((rand.Float64()*2 - 1) * float64(half) * jitterFrac)
		half += delta
	}
	return notBefore.Add(half)
}
