package sleep

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLoadMissingFile(t *testing.T) {
	stateDir := t.TempDir()
	state, err := Load(stateDir)
	if err != nil {
		t.Fatalf("Load() should not error on missing file, got: %v", err)
	}
	if !state.Until.IsZero() || state.Reason != "" {
		t.Fatalf("Load() should return zero-value State on missing file, got: %+v", state)
	}
}

func TestSetWritesFile(t *testing.T) {
	stateDir := t.TempDir()
	dur := 5 * time.Minute
	reason := "test sleep"

	beforeSet := time.Now()
	state, err := Set(stateDir, dur, reason)
	afterSet := time.Now()

	if err != nil {
		t.Fatalf("Set() failed: %v", err)
	}

	if state.Reason != reason {
		t.Fatalf("Set() returned state with wrong reason: got %q, want %q", state.Reason, reason)
	}

	expectedMinTime := beforeSet.Add(dur)
	expectedMaxTime := afterSet.Add(dur)

	if state.Until.Before(expectedMinTime) || state.Until.After(expectedMaxTime) {
		t.Fatalf("Set() returned state with wrong Until: got %v, expected between %v and %v", state.Until, expectedMinTime, expectedMaxTime)
	}

	// Verify file was written
	filePath := filepath.Join(stateDir, sleepFile)
	if _, err := os.Stat(filePath); err != nil {
		t.Fatalf("sleep.json file was not created: %v", err)
	}

	// Check file permissions
	info, err := os.Stat(filePath)
	if err != nil {
		t.Fatalf("Could not stat file: %v", err)
	}
	perms := info.Mode().Perm()
	if perms != 0o600 {
		t.Fatalf("sleep.json has wrong permissions: got %o, want 0o600", perms)
	}
}

func TestIsSleeping(t *testing.T) {
	// Test when Until is zero (not sleeping)
	state := State{}
	if state.IsSleeping() {
		t.Errorf("IsSleeping() should be false for zero-value State")
	}

	// Test when Until is in the past (not sleeping)
	state.Until = time.Now().Add(-1 * time.Minute)
	if state.IsSleeping() {
		t.Errorf("IsSleeping() should be false when Until is in the past")
	}

	// Test when Until is in the future (sleeping)
	state.Until = time.Now().Add(5 * time.Minute)
	if !state.IsSleeping() {
		t.Errorf("IsSleeping() should be true when Until is in the future")
	}
}

func TestClearRemovesFile(t *testing.T) {
	stateDir := t.TempDir()

	// Set up a sleep state
	_, err := Set(stateDir, 5*time.Minute, "test")
	if err != nil {
		t.Fatalf("Set() failed: %v", err)
	}

	// Verify file exists
	filePath := filepath.Join(stateDir, sleepFile)
	if _, err := os.Stat(filePath); err != nil {
		t.Fatalf("File should exist after Set(), but got: %v", err)
	}

	// Clear
	err = Clear(stateDir)
	if err != nil {
		t.Fatalf("Clear() failed: %v", err)
	}

	// Verify file is gone
	if _, err := os.Stat(filePath); !os.IsNotExist(err) {
		t.Fatalf("File should not exist after Clear(), but got: %v", err)
	}
}

func TestClearNonexistentFileNoError(t *testing.T) {
	stateDir := t.TempDir()
	err := Clear(stateDir)
	if err != nil {
		t.Fatalf("Clear() should not error when file doesn't exist, got: %v", err)
	}
}

func TestRoundTripSetLoadMatch(t *testing.T) {
	stateDir := t.TempDir()
	dur := 10 * time.Minute
	reason := "round trip test"

	originalState, err := Set(stateDir, dur, reason)
	if err != nil {
		t.Fatalf("Set() failed: %v", err)
	}

	loadedState, err := Load(stateDir)
	if err != nil {
		t.Fatalf("Load() failed: %v", err)
	}

	if loadedState.Reason != originalState.Reason {
		t.Fatalf("Loaded Reason mismatch: got %q, want %q", loadedState.Reason, originalState.Reason)
	}

	if !loadedState.Until.Equal(originalState.Until) {
		t.Fatalf("Loaded Until mismatch: got %v, want %v", loadedState.Until, originalState.Until)
	}
}

func TestJSONFormatStable(t *testing.T) {
	stateDir := t.TempDir()
	_, err := Set(stateDir, 5*time.Minute, "format test")
	if err != nil {
		t.Fatalf("Set() failed: %v", err)
	}

	filePath := filepath.Join(stateDir, sleepFile)
	data, err := os.ReadFile(filePath)
	if err != nil {
		t.Fatalf("Could not read sleep.json: %v", err)
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("sleep.json is not valid JSON: %v", err)
	}

	if _, hasUntil := parsed["until"]; !hasUntil {
		t.Fatalf("sleep.json missing 'until' field")
	}
	if _, hasReason := parsed["reason"]; !hasReason {
		t.Fatalf("sleep.json missing 'reason' field")
	}

	// Verify it's readable as State
	var state State
	if err := json.Unmarshal(data, &state); err != nil {
		t.Fatalf("sleep.json cannot unmarshal to State: %v", err)
	}
}
