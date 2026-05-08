package main

import (
	"testing"
)

func TestUninstallCmd(t *testing.T) {
	// Basic sanity test: command parses.
	cmd := newUninstallCmd()
	if cmd.Use != "uninstall" {
		t.Errorf("expected Use 'uninstall', got %q", cmd.Use)
	}
	if cmd.Short == "" {
		t.Error("expected Short description")
	}
}

func TestUninstallCmdFlags(t *testing.T) {
	cmd := newUninstallCmd()
	flags := cmd.Flags()

	if flags.Lookup("purge") == nil {
		t.Error("expected --purge flag")
	}

	if flags.Lookup("keep") == nil {
		t.Error("expected --keep flag")
	}

	if flags.Lookup("dir") == nil {
		t.Error("expected --dir flag")
	}
}
