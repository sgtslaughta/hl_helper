package main

import (
	"testing"
)

func TestInstallCmd(t *testing.T) {
	// Basic sanity test: command parses.
	cmd := newInstallCmd()
	if cmd.Use != "install" {
		t.Errorf("expected Use 'install', got %q", cmd.Use)
	}
	if cmd.Short == "" {
		t.Error("expected Short description")
	}
}

func TestInstallCmdFlags(t *testing.T) {
	cmd := newInstallCmd()
	flags := cmd.Flags()

	if flags.Lookup("server") == nil {
		t.Error("expected --server flag")
	}

	if flags.Lookup("token") == nil {
		t.Error("expected --token flag")
	}

	if flags.Lookup("dir") == nil {
		t.Error("expected --dir flag")
	}

	if flags.Lookup("unattended") == nil {
		t.Error("expected --unattended flag")
	}

	if flags.Lookup("fetch") == nil {
		t.Error("expected --fetch flag")
	}
}
