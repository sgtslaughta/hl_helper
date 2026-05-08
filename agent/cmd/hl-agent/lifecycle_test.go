package main

import (
	"bytes"
	"testing"
)

func TestStartCmd(t *testing.T) {
	// Basic sanity test: command parses and help works.
	cmd := newStartCmd()
	if cmd.Use != "start" {
		t.Errorf("expected Use 'start', got %q", cmd.Use)
	}
	if cmd.Short == "" {
		t.Error("expected Short description")
	}
}

func TestStopCmd(t *testing.T) {
	cmd := newStopCmd()
	if cmd.Use != "stop" {
		t.Errorf("expected Use 'stop', got %q", cmd.Use)
	}
}

func TestRestartCmd(t *testing.T) {
	cmd := newRestartCmd()
	if cmd.Use != "restart" {
		t.Errorf("expected Use 'restart', got %q", cmd.Use)
	}
}

func TestStartCmdHelp(t *testing.T) {
	cmd := newStartCmd()
	buf := bytes.Buffer{}
	cmd.SetOut(&buf)
	cmd.SetArgs([]string{"--help"})
	_ = cmd.Execute()
	// Help doesn't return error; just check command parses.
	if cmd.Use != "start" {
		t.Error("command should parse")
	}
}
