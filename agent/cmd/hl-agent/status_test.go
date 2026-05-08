package main

import (
	"testing"
)

func TestStatusCmd(t *testing.T) {
	// Basic sanity test: command parses.
	cmd := newStatusCmd()
	if cmd.Use != "status" {
		t.Errorf("expected Use 'status', got %q", cmd.Use)
	}
	if cmd.Short == "" {
		t.Error("expected Short description")
	}
}

func TestStatusCmdWatch(t *testing.T) {
	// Skip CLI test for --watch (TUI plumbing tested separately via dashboard_test.go).
	t.Skip("--watch CLI test skipped (TUI render logic tested via dashboard_test.go)")
}
