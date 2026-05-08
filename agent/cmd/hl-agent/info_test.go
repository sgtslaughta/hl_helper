package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/hlhelper/hl-agent/internal/hostinfo"
	"github.com/hlhelper/hl-agent/internal/manifest"
)

func TestInfoCmd(t *testing.T) {
	dir := t.TempDir()

	// Write a fake manifest.
	m := manifest.Manifest{
		HostID:       "test-host-123",
		GRPCEndpoint: "grpc.example.com:443",
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(dir, "manifest.json"), data, 0o600)

	// Run the command (styled table).
	cmd := newInfoCmd()
	cmd.SetArgs([]string{"--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if !containsSubstring(output, "host_id") || !containsSubstring(output, "test-host-123") {
		t.Errorf("expected host_id in output, got: %q", output)
	}
}

func TestInfoCmdJSON(t *testing.T) {
	dir := t.TempDir()

	// Write a fake manifest.
	m := manifest.Manifest{
		HostID:       "test-host-456",
		GRPCEndpoint: "grpc.example.com:443",
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(dir, "manifest.json"), data, 0o600)

	// Run the command with --json.
	cmd := newInfoCmd()
	cmd.SetArgs([]string{"--dir", dir, "--json"})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Parse the JSON output.
	output := buf.String()
	var info hostinfo.HostInfo
	if err := json.Unmarshal([]byte(output), &info); err != nil {
		t.Fatalf("invalid json output: %v", err)
	}

	if info.HostID != "test-host-456" {
		t.Errorf("expected host_id 'test-host-456', got %q", info.HostID)
	}
}
