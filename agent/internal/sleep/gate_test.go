package sleep

import (
	"testing"
	"time"
)

func TestCheckNotSleeping(t *testing.T) {
	stateDir := t.TempDir()
	sleeping, until := Check(stateDir)
	if sleeping {
		t.Errorf("Check() should return false when no sleep state exists, got %v", sleeping)
	}
	if !until.IsZero() {
		t.Errorf("Check() should return zero time when not sleeping, got %v", until)
	}
}

func TestCheckSleeping(t *testing.T) {
	stateDir := t.TempDir()
	dur := 5 * time.Minute
	_, err := Set(stateDir, dur, "test sleep")
	if err != nil {
		t.Fatalf("Set() failed: %v", err)
	}

	sleeping, until := Check(stateDir)
	if !sleeping {
		t.Errorf("Check() should return true when sleep state is active, got %v", sleeping)
	}
	if until.IsZero() {
		t.Errorf("Check() should return non-zero until time when sleeping, got %v", until)
	}
	if time.Now().After(until) {
		t.Errorf("Check() returned until time in the past: %v", until)
	}
}
