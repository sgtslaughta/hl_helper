package main

import (
	"testing"
)

func TestLogsCmd(t *testing.T) {
	// Basic sanity test: command parses.
	cmd := newLogsCmd()
	if cmd.Use != "logs" {
		t.Errorf("expected Use 'logs', got %q", cmd.Use)
	}
	if cmd.Short == "" {
		t.Error("expected Short description")
	}
}

func TestLogsCmdFlags(t *testing.T) {
	cmd := newLogsCmd()
	flags := cmd.Flags()

	if flags.Lookup("follow") == nil {
		t.Error("expected --follow flag")
	}

	if flags.Lookup("lines") == nil {
		t.Error("expected --lines flag")
	}

	if flags.Lookup("name") == nil {
		t.Error("expected --name flag")
	}
}
