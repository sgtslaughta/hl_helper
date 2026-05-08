package tui

import (
	"testing"
)

func TestWizardConfigDefaults(t *testing.T) {
	cfg := WizardConfig{
		InitKind: "systemd",
		Server:   "http://localhost:8080",
		Token:    "test-token",
		Hostname: "test-host",
	}

	if cfg.InitKind != "systemd" {
		t.Errorf("expected InitKind 'systemd', got %q", cfg.InitKind)
	}
	if cfg.Server != "http://localhost:8080" {
		t.Errorf("expected Server, got %q", cfg.Server)
	}
	if cfg.Token != "test-token" {
		t.Errorf("expected Token, got %q", cfg.Token)
	}
	if cfg.Hostname != "test-host" {
		t.Errorf("expected Hostname, got %q", cfg.Hostname)
	}
}

func TestWizardResultStructure(t *testing.T) {
	res := WizardResult{
		Server:    "http://test",
		Token:     "token123",
		Hostname:  "myhost",
		Confirmed: true,
	}

	if res.Server != "http://test" {
		t.Errorf("expected Server, got %q", res.Server)
	}
	if res.Token != "token123" {
		t.Errorf("expected Token, got %q", res.Token)
	}
	if res.Hostname != "myhost" {
		t.Errorf("expected Hostname, got %q", res.Hostname)
	}
	if !res.Confirmed {
		t.Error("expected Confirmed to be true")
	}
}
