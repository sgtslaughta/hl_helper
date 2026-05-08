package main

import (
	"bytes"
	"strings"
	"testing"

	"github.com/hlhelper/hl-agent/internal/manifest"
)

func TestSetEndpointCmd_UpdatesManifest(t *testing.T) {
	dir := t.TempDir()
	m := manifest.Manifest{HostID: "h1", GRPCEndpoint: "old:443"}
	if err := m.Save(dir); err != nil {
		t.Fatalf("save manifest: %v", err)
	}

	cmd := newSetEndpointCmd()
	var stdout bytes.Buffer
	cmd.SetOut(&stdout)
	cmd.SetErr(&stdout)
	cmd.SetArgs([]string{"--dir", dir, "new.host.example.com:8443"})

	if err := cmd.Execute(); err != nil {
		t.Fatalf("execute: %v", err)
	}

	got, err := manifest.Load(dir)
	if err != nil {
		t.Fatalf("reload manifest: %v", err)
	}
	if got.GRPCEndpoint != "new.host.example.com:8443" {
		t.Errorf("endpoint = %q, want new.host.example.com:8443", got.GRPCEndpoint)
	}
	if got.HostID != "h1" {
		t.Errorf("HostID changed unexpectedly: %q", got.HostID)
	}
	if !strings.Contains(stdout.String(), "endpoint updated") {
		t.Errorf("missing success message: %s", stdout.String())
	}
}

func TestSetEndpointCmd_RejectsMissingPort(t *testing.T) {
	dir := t.TempDir()
	m := manifest.Manifest{HostID: "h1", GRPCEndpoint: "old:443"}
	_ = m.Save(dir)

	cmd := newSetEndpointCmd()
	cmd.SetOut(&bytes.Buffer{})
	cmd.SetErr(&bytes.Buffer{})
	cmd.SetArgs([]string{"--dir", dir, "no-port-host"})

	if err := cmd.Execute(); err == nil {
		t.Fatalf("expected error for missing port, got nil")
	}
}

func TestShowEndpointCmd(t *testing.T) {
	dir := t.TempDir()
	m := manifest.Manifest{HostID: "h99", GRPCEndpoint: "fleet:9000"}
	_ = m.Save(dir)

	cmd := newShowEndpointCmd()
	var out bytes.Buffer
	cmd.SetOut(&out)
	cmd.SetErr(&out)
	cmd.SetArgs([]string{"--dir", dir})

	if err := cmd.Execute(); err != nil {
		t.Fatalf("execute: %v", err)
	}
	s := out.String()
	if !strings.Contains(s, "h99") || !strings.Contains(s, "fleet:9000") {
		t.Errorf("output missing fields: %s", s)
	}
}
