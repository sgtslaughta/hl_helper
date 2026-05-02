package manifest

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultManifestAllowsCoreActions(t *testing.T) {
	m := DefaultManifest()

	coreActions := []string{
		"pkg.update",
		"reboot",
		"shell.exec",
		"get_facts",
		"docker.op",
		"plugin.invoke",
		"terminal.open",
		"file.transfer",
	}

	for _, action := range coreActions {
		if !m.AllowsAction(action) {
			t.Errorf("DefaultManifest should allow %q", action)
		}
	}
}

func TestSaveLoadRoundtrip(t *testing.T) {
	m := Manifest{
		HostID:               "host-123",
		GRPCEndpoint:         "localhost:9090",
		ServerSigningPubKeyB64: "dGVzdGtleTEyMzQ1Ng==",
		AllowedActions:       []string{"pkg.update", "reboot"},
		MaxRisk:              "medium",
	}

	dir := t.TempDir()

	// Save
	if err := m.Save(dir); err != nil {
		t.Fatalf("Save failed: %v", err)
	}

	// Check file exists
	path := filepath.Join(dir, "manifest.json")
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("manifest.json not created: %v", err)
	}

	// Load
	loaded, err := Load(dir)
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}

	// Compare
	if loaded.HostID != m.HostID {
		t.Errorf("HostID mismatch: got %q, want %q", loaded.HostID, m.HostID)
	}
	if loaded.GRPCEndpoint != m.GRPCEndpoint {
		t.Errorf("GRPCEndpoint mismatch: got %q, want %q", loaded.GRPCEndpoint, m.GRPCEndpoint)
	}
	if loaded.ServerSigningPubKeyB64 != m.ServerSigningPubKeyB64 {
		t.Errorf("ServerSigningPubKeyB64 mismatch")
	}
	if len(loaded.AllowedActions) != len(m.AllowedActions) {
		t.Errorf("AllowedActions length mismatch")
	}
	if loaded.MaxRisk != m.MaxRisk {
		t.Errorf("MaxRisk mismatch")
	}
}

func TestAllowsActionRespectsList(t *testing.T) {
	m := Manifest{
		AllowedActions: []string{"pkg.update", "reboot"},
	}

	tests := []struct {
		action   string
		allowed  bool
	}{
		{"pkg.update", true},
		{"reboot", true},
		{"shell.exec", false},
		{"nonexistent", false},
	}

	for _, tt := range tests {
		result := m.AllowsAction(tt.action)
		if result != tt.allowed {
			t.Errorf("AllowsAction(%q): got %v, want %v", tt.action, result, tt.allowed)
		}
	}
}

func TestAllowsRiskOrderingLowLessThanCritical(t *testing.T) {
	tests := []struct {
		maxRisk  string
		risk     string
		allowed  bool
	}{
		{"low", "low", true},
		{"low", "medium", false},
		{"low", "high", false},
		{"low", "critical", false},
		{"medium", "low", true},
		{"medium", "medium", true},
		{"medium", "high", false},
		{"medium", "critical", false},
		{"high", "low", true},
		{"high", "medium", true},
		{"high", "high", true},
		{"high", "critical", false},
		{"critical", "critical", true},
	}

	for _, tt := range tests {
		m := Manifest{MaxRisk: tt.maxRisk}
		result := m.AllowsRisk(tt.risk)
		if result != tt.allowed {
			t.Errorf("Manifest{MaxRisk:%q}.AllowsRisk(%q): got %v, want %v",
				tt.maxRisk, tt.risk, result, tt.allowed)
		}
	}
}
