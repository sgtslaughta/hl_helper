package main

import (
	"bytes"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/sleep"
)

func TestSleepCmd(t *testing.T) {
	dir := t.TempDir()

	// Run sleep command with 1m duration.
	cmd := newSleepCmd()
	cmd.SetArgs([]string{"1m", "--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if !containsSubstring(output, "sleeping") {
		t.Errorf("expected 'sleeping' in output, got: %q", output)
	}

	// Verify sleep state file was written.
	state, err := sleep.Load(dir)
	if err != nil {
		t.Fatalf("load sleep state: %v", err)
	}

	if !state.IsSleeping() {
		t.Error("expected agent to be sleeping")
	}
}

func TestResumeCmd(t *testing.T) {
	dir := t.TempDir()

	// First sleep.
	_, _ = sleep.Set(dir, 1*time.Hour, "test")

	// Then resume.
	cmd := newResumeCmd()
	cmd.SetArgs([]string{"--dir", dir})
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetErr(&bytes.Buffer{})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	output := buf.String()
	if !containsSubstring(output, "resumed") {
		t.Errorf("expected 'resumed' in output, got: %q", output)
	}

	// Verify sleep state is cleared.
	state, _ := sleep.Load(dir)
	if state.IsSleeping() {
		t.Error("expected agent to not be sleeping after resume")
	}
}
