package hostinfo

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestCollect_WithValidManifest(t *testing.T) {
	// TempDir setup: write a fake manifest.json with HostID + GrpcEndpoint
	tempDir := t.TempDir()

	manifest := map[string]interface{}{
		"host_id":       "test-host-123",
		"grpc_endpoint": "localhost:9090",
	}
	manifestPath := filepath.Join(tempDir, "manifest.json")
	data, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(manifestPath, data, 0644); err != nil {
		t.Fatal(err)
	}

	// Call Collect
	info := Collect(tempDir, "1.2.3")

	// Assert fields are populated
	if info.HostID != "test-host-123" {
		t.Errorf("HostID: got %q, want %q", info.HostID, "test-host-123")
	}
	if info.GrpcEndpoint != "localhost:9090" {
		t.Errorf("GrpcEndpoint: got %q, want %q", info.GrpcEndpoint, "localhost:9090")
	}
	if info.AgentVersion != "1.2.3" {
		t.Errorf("AgentVersion: got %q, want %q", info.AgentVersion, "1.2.3")
	}

	// Hostname, OS, Arch should always be set
	if info.Hostname == "" {
		t.Error("Hostname should not be empty")
	}
	if info.OS == "" {
		t.Error("OS should not be empty")
	}
	if info.Arch == "" {
		t.Error("Arch should not be empty")
	}
}

func TestCollect_EmptyDir(t *testing.T) {
	// Empty dir test: returns zero-valued HostID etc but Hostname/OS still set
	tempDir := t.TempDir()

	info := Collect(tempDir, "1.0.0")

	if info.HostID != "" {
		t.Errorf("HostID: got %q, want empty", info.HostID)
	}
	if info.GrpcEndpoint != "" {
		t.Errorf("GrpcEndpoint: got %q, want empty", info.GrpcEndpoint)
	}
	if info.Hostname == "" {
		t.Error("Hostname should not be empty even with empty dir")
	}
	if info.OS == "" {
		t.Error("OS should not be empty")
	}
}

func TestCollect_SleepFilePresent(t *testing.T) {
	// Sleep file present: Sleeping=true, SleepUntil set
	tempDir := t.TempDir()

	futureTime := time.Now().Add(1 * time.Hour)
	sleepData := map[string]interface{}{
		"until": futureTime,
	}
	sleepPath := filepath.Join(tempDir, "sleep.json")
	data, err := json.Marshal(sleepData)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(sleepPath, data, 0644); err != nil {
		t.Fatal(err)
	}

	info := Collect(tempDir, "1.0.0")

	if !info.Sleeping {
		t.Error("Sleeping: got false, want true")
	}
	if info.SleepUntil.IsZero() {
		t.Error("SleepUntil: should not be zero when sleep file is present")
	}
}

func TestCollect_SleepFileExpired(t *testing.T) {
	// Sleep file expired: Sleeping=false
	tempDir := t.TempDir()

	pastTime := time.Now().Add(-1 * time.Hour)
	sleepData := map[string]interface{}{
		"until": pastTime,
	}
	sleepPath := filepath.Join(tempDir, "sleep.json")
	data, err := json.Marshal(sleepData)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(sleepPath, data, 0644); err != nil {
		t.Fatal(err)
	}

	info := Collect(tempDir, "1.0.0")

	if info.Sleeping {
		t.Error("Sleeping: got true, want false (sleep time has expired)")
	}
}

func TestCollect_NoKeystoreRequired(t *testing.T) {
	// Test must not require the keystore to exist (cert read is best-effort)
	tempDir := t.TempDir()

	info := Collect(tempDir, "1.0.0")

	// Should not panic or error, CertNotAfter should be zero
	if !info.CertNotAfter.IsZero() {
		t.Errorf("CertNotAfter: got %v, want zero-valued", info.CertNotAfter)
	}
}
