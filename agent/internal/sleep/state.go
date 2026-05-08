package sleep

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

const sleepFile = "sleep.json"

type State struct {
	Until  time.Time `json:"until"`
	Reason string    `json:"reason"`
}

// Load reads the sleep state from stateDir/sleep.json.
// If the file does not exist, returns zero-value State with no error.
func Load(stateDir string) (State, error) {
	filePath := filepath.Join(stateDir, sleepFile)
	data, err := os.ReadFile(filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return State{}, nil
		}
		return State{}, err
	}

	var state State
	if err := json.Unmarshal(data, &state); err != nil {
		return State{}, err
	}
	return state, nil
}

// IsSleeping returns true if Until is not zero and is in the future.
func (s State) IsSleeping() bool {
	return !s.Until.IsZero() && time.Now().Before(s.Until)
}

// Set writes a sleep state to stateDir/sleep.json with the given duration and reason.
// until is calculated as now + dur. File is written with 0o600 permissions.
// Returns the State that was written.
func Set(stateDir string, dur time.Duration, reason string) (State, error) {
	if err := os.MkdirAll(stateDir, 0o755); err != nil {
		return State{}, err
	}

	state := State{
		Until:  time.Now().Add(dur),
		Reason: reason,
	}

	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return State{}, err
	}

	filePath := filepath.Join(stateDir, sleepFile)
	if err := os.WriteFile(filePath, data, 0o600); err != nil {
		return State{}, err
	}

	return state, nil
}

// Clear removes the sleep state file from stateDir.
// Returns nil if the file does not exist.
func Clear(stateDir string) error {
	filePath := filepath.Join(stateDir, sleepFile)
	if err := os.Remove(filePath); err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	return nil
}
