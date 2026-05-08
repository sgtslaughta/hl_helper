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
