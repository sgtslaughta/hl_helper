package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/hlhelper/hl-agent/internal/manifest"
)

func TestGetHostID(t *testing.T) {
	dir := t.TempDir()

	// Write a fake manifest.
	m := manifest.Manifest{
		HostID:       "test-host-123",
		GRPCEndpoint: "example.com:443",
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(dir, "manifest.json"), data, 0o600)

	// Run the command.
	cmd := newGetHostIDCmd()
	cmd.SetArgs([]string{"--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if output != "test-host-123\n" {
		t.Errorf("expected 'test-host-123\\n', got %q", output)
	}
}

func TestGetEndpoint(t *testing.T) {
	dir := t.TempDir()

	// Write a fake manifest.
	m := manifest.Manifest{
		HostID:       "test-host-123",
		GRPCEndpoint: "grpc.example.com:443",
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(dir, "manifest.json"), data, 0o600)

	// Run the command.
	cmd := newGetEndpointCmd()
	cmd.SetArgs([]string{"--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if output != "grpc.example.com:443\n" {
		t.Errorf("expected 'grpc.example.com:443\\n', got %q", output)
	}
}

func TestGetConfig(t *testing.T) {
	dir := t.TempDir()

	// Write a fake manifest.
	m := manifest.Manifest{
		HostID:       "test-host-123",
		GRPCEndpoint: "grpc.example.com:443",
		MaxRisk:      "high",
	}
	data, _ := json.Marshal(m)
	os.WriteFile(filepath.Join(dir, "manifest.json"), data, 0o600)

	// Run the command.
	cmd := newGetConfigCmd()
	cmd.SetArgs([]string{"--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if !containsSubstring(output, "host_id") || !containsSubstring(output, "endpoint") {
		t.Errorf("output missing expected fields: %q", output)
	}
}

func containsSubstring(s, sub string) bool {
	return bytes.Contains([]byte(s), []byte(sub))
}
