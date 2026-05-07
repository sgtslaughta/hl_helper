package updater

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"
)

type State struct {
	CurrentVersion  string    `json:"current_version"`
	PreviousVersion string    `json:"previous_version"`
	PreviousBinary  string    `json:"previous_binary"`
	UpdatedAt       time.Time `json:"updated_at"`
}

const (
	stateFile   = "updater.json"
	pendingFile = ".pending"
)

func ReadState(dir string) (State, error) {
	var s State
	b, err := os.ReadFile(filepath.Join(dir, stateFile))
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return s, err
	}
	if err := json.Unmarshal(b, &s); err != nil {
		return s, err
	}
	return s, nil
}

func WriteState(dir string, s State) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	s.UpdatedAt = time.Now().UTC()
	b, err := json.Marshal(s)
	if err != nil {
		return err
	}
	tmp := filepath.Join(dir, stateFile+".tmp")
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, filepath.Join(dir, stateFile))
}

type pendingPayload struct {
	Target   string `json:"target"`
	Previous string `json:"previous"`
}

func MarkPending(dir, target, previous string) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	b, err := json.Marshal(pendingPayload{Target: target, Previous: previous})
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, pendingFile), b, 0o644)
}

func ReadPending(dir string) (target, previous string, ok bool) {
	b, err := os.ReadFile(filepath.Join(dir, pendingFile))
	if err != nil {
		return "", "", false
	}
	var p pendingPayload
	if json.Unmarshal(b, &p) != nil {
		return "", "", false
	}
	return p.Target, p.Previous, true
}

func ClearPending(dir string) error {
	err := os.Remove(filepath.Join(dir, pendingFile))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}
