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

func TestComputeRotateAfter50Percent(t *testing.T) {
	now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)
	notBefore := now.Add(-12 * time.Hour)
	notAfter := now.Add(12 * time.Hour)
	// Total TTL = 24h. 50% point = notBefore + 12h = now.
	// With 0 jitter, rotateAfter should be ~now (i.e. immediate).

	ra := ComputeRotateAfter(notBefore, notAfter, now, 0.0)
	if ra.After(now.Add(1*time.Second)) || ra.Before(now.Add(-1*time.Second)) {
		t.Errorf("rotateAfter = %v, want ~%v", ra, now)
	}
}

func TestComputeRotateAfterAppliesJitter(t *testing.T) {
	now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)
	notBefore := now.Add(-1 * time.Hour)
	notAfter := now.Add(7 * 24 * time.Hour) // 7d TTL roughly (169h span)
	// 50% = 84.5h from notBefore => 83.5h from now.
	// With 10% jitter, should fall in [75h, 92h] from now (approx).

	for i := 0; i < 50; i++ {
		ra := ComputeRotateAfter(notBefore, notAfter, now, 0.10)
		dist := ra.Sub(now)
		if dist < 75*time.Hour || dist > 92*time.Hour {
			t.Errorf("iter %d: dist=%v out of band", i, dist)
		}
	}
}
