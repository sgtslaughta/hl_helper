package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/hlhelper/hl-agent/internal/manifest"
)

func TestCheckManifest(t *testing.T) {
	dir := t.TempDir()

	// Missing manifest.
	result := checkManifest(dir)
	if result.pass {
		t.Error("expected manifest check to fail when missing")
	}

	// Write manifest.
	m := manifest.Manifest{
		HostID:       "test-host",
		GRPCEndpoint: "example.com:443",
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(dir, "manifest.json"), data, 0o600)

	result = checkManifest(dir)
	if !result.pass {
		t.Errorf("expected manifest check to pass, got: %v", result.msg)
	}
}

func TestCheckStateDir(t *testing.T) {
	dir := t.TempDir()

	result := checkStateDir(dir)
	if !result.pass {
		t.Errorf("expected state dir check to pass, got: %v", result.msg)
	}
}

func TestCheckRotatorState(t *testing.T) {
	dir := t.TempDir()

	// When rotator.state.json doesn't exist, should pass with "not yet initialized"
	result := checkRotatorState(dir)
	if !result.pass {
		t.Errorf("expected rotator state check to pass when missing, got: %v", result.msg)
	}

	// Write a NORMAL state
	stateFile := filepath.Join(dir, "rotator.state.json")
	normalState := []byte(`{"phase":"NORMAL","consecutive_failures":0}`)
	if err := os.WriteFile(stateFile, normalState, 0o600); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}
	result = checkRotatorState(dir)
	if !result.pass || result.warn {
		t.Errorf("expected NORMAL state to pass (no warn), got pass=%v warn=%v msg=%q", result.pass, result.warn, result.msg)
	}

	// Write a ROTATE_BACKOFF state
	backoffState := []byte(`{"phase":"ROTATE_BACKOFF","consecutive_failures":3}`)
	if err := os.WriteFile(stateFile, backoffState, 0o600); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}
	result = checkRotatorState(dir)
	if !result.pass || !result.warn {
		t.Errorf("expected ROTATE_BACKOFF state to pass with warn, got pass=%v warn=%v", result.pass, result.warn)
	}

	// Write a HALTED state
	haltedState := []byte(`{"phase":"HALTED","consecutive_failures":5,"halted_reason":"sig-mismatch"}`)
	if err := os.WriteFile(stateFile, haltedState, 0o600); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}
	result = checkRotatorState(dir)
	if result.pass {
		t.Errorf("expected HALTED state to fail, got pass=%v", result.pass)
	}
}

func TestDoctorCmd(t *testing.T) {
	dir := t.TempDir()

	// Write minimal manifest.
	m := manifest.Manifest{
		HostID:       "test-host",
		GRPCEndpoint: "example.com:443",
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(dir, "manifest.json"), data, 0o600)

	cmd := newDoctorCmd()
	cmd.SetArgs([]string{"--dir", dir})

	// We expect this to fail because keystore won't exist,
	// but it should not panic.
	_ = cmd.Execute()
}
