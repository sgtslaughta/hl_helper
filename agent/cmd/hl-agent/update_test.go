package main

import (
	"bytes"
	"testing"
)

func TestUpdateCmd(t *testing.T) {
	dir := t.TempDir()

	cmd := newUpdateCmd()
	cmd.SetArgs([]string{"--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	// Should run without error (no-op for now).
	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if output == "" {
		t.Error("expected output from update command")
	}
}

func TestUpdateCheckCmd(t *testing.T) {
	dir := t.TempDir()

	cmd := newUpdateCmd()
	cmd.SetArgs([]string{"--check", "--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if !containsSubstring(output, "version") {
		t.Errorf("expected version in output, got: %q", output)
	}
}
