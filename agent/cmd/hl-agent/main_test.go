package main

import (
	"bytes"
	"runtime"
	"strings"
	"testing"
)

func TestVersionPrintsExpectedFields(t *testing.T) {
	buf := &bytes.Buffer{}
	cmd := newRootCmd()
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{"version"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("version command failed: %v", err)
	}

	output := buf.String()
	if !strings.Contains(output, "hl-agent version dev") {
		t.Errorf("output missing 'hl-agent version dev': %s", output)
	}
	if !strings.Contains(output, "commit:") {
		t.Errorf("output missing 'commit:' prefix: %s", output)
	}
	if !strings.Contains(output, "go:") {
		t.Errorf("output missing 'go:' prefix: %s", output)
	}
}

func TestUnknownCommandFails(t *testing.T) {
	buf := &bytes.Buffer{}
	cmd := newRootCmd()
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{"bogus"})

	err := cmd.Execute()
	if err == nil {
		t.Fatal("bogus command should have failed but returned no error")
	}
}

func TestEnrollSubcommandIsRegistered(t *testing.T) {
	buf := &bytes.Buffer{}
	cmd := newRootCmd()
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{"enroll", "--help"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("enroll --help failed: %v", err)
	}

	output := buf.String()
	if !strings.Contains(output, "enroll") {
		t.Errorf("output missing 'enroll': %s", output)
	}
}

func TestServiceSubcommandIsRegistered(t *testing.T) {
	buf := &bytes.Buffer{}
	cmd := newRootCmd()
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{"service", "--help"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("service --help failed: %v", err)
	}

	output := buf.String()
	if !strings.Contains(output, "service") {
		t.Errorf("output missing 'service': %s", output)
	}
}

func TestDecommissionSubcommandIsRegistered(t *testing.T) {
	buf := &bytes.Buffer{}
	cmd := newRootCmd()
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{"decommission", "--help"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("decommission --help failed: %v", err)
	}

	output := buf.String()
	if !strings.Contains(output, "decommission") {
		t.Errorf("output missing 'decommission': %s", output)
	}
}

func TestRootHelpListsAllSubcommands(t *testing.T) {
	buf := &bytes.Buffer{}
	cmd := newRootCmd()
	cmd.SetOut(buf)
	cmd.SetErr(buf)
	cmd.SetArgs([]string{"--help"})

	err := cmd.Execute()
	if err != nil {
		t.Fatalf("--help failed: %v", err)
	}

	output := buf.String()
	requiredSubcommands := []string{"version", "enroll", "service", "decommission", "rotate-signing-key"}
	for _, sub := range requiredSubcommands {
		if !strings.Contains(output, sub) {
			t.Errorf("output missing '%s': %s", sub, output)
		}
	}
}
