package rotator

import (
	"path/filepath"
	"testing"
	"time"
)

func TestStateRoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "rotator.state.json")

	s := State{
		Phase:               StateNormal,
		LastAttemptAt:       time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC),
		ConsecutiveFailures: 0,
	}
	if err := SaveState(path, s); err != nil {
		t.Fatalf("SaveState: %v", err)
	}
	loaded, err := LoadState(path)
	if err != nil {
		t.Fatalf("LoadState: %v", err)
	}
	if loaded.Phase != StateNormal {
		t.Errorf("Phase = %v, want %v", loaded.Phase, StateNormal)
	}
}

func TestLoadStateMissingReturnsDefault(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "nope.json")
	s, err := LoadState(path)
	if err != nil {
		t.Fatalf("LoadState: %v", err)
	}
	if s.Phase != StateNormal {
		t.Errorf("default Phase = %v, want %v", s.Phase, StateNormal)
	}
}

func TestStateHaltedSticky(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "s.json")
	s := State{Phase: StateHalted, HaltedReason: "sig-mismatch"}
	if err := SaveState(path, s); err != nil {
		t.Fatalf("SaveState: %v", err)
	}
	loaded, _ := LoadState(path)
	if loaded.Phase != StateHalted {
		t.Errorf("expected sticky halted")
	}
	if loaded.HaltedReason != "sig-mismatch" {
		t.Errorf("HaltedReason = %q", loaded.HaltedReason)
	}
}
