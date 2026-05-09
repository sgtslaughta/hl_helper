package inventory

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCollectLangPackages(t *testing.T) {
	// Create temp directory structure
	tmpdir := t.TempDir()

	// Create pip site-packages structure
	sitePackages := filepath.Join(tmpdir, "site-packages")
	os.MkdirAll(filepath.Join(sitePackages, "requests-2.28.0.dist-info"), 0755)
	os.WriteFile(
		filepath.Join(sitePackages, "requests-2.28.0.dist-info", "METADATA"),
		[]byte("Name: requests\nVersion: 2.28.0\n"),
		0644,
	)

	// Create npm node_modules structure
	nodeModules := filepath.Join(tmpdir, "node_modules", "axios")
	os.MkdirAll(nodeModules, 0755)
	os.WriteFile(
		filepath.Join(nodeModules, "package.json"),
		[]byte(`{"name":"axios","version":"1.4.0"}`),
		0644,
	)

	pkgs, err := CollectLangPackages([]string{tmpdir})
	if err != nil {
		t.Fatalf("CollectLangPackages failed: %v", err)
	}

	// Should find both pip and npm packages
	if len(pkgs) < 2 {
		t.Errorf("got %d packages, want at least 2", len(pkgs))
	}

	// Verify pip package
	var foundPip bool
	for _, pkg := range pkgs {
		if pkg.Ecosystem == "pip" && pkg.Name == "requests" {
			if pkg.Version != "2.28.0" {
				t.Errorf("pip package version: got %q, want 2.28.0", pkg.Version)
			}
			foundPip = true
		}
	}
	if !foundPip {
		t.Error("pip package not found")
	}

	// Verify npm package
	var foundNPM bool
	for _, pkg := range pkgs {
		if pkg.Ecosystem == "npm" && pkg.Name == "axios" {
			if pkg.Version != "1.4.0" {
				t.Errorf("npm package version: got %q, want 1.4.0", pkg.Version)
			}
			foundNPM = true
		}
	}
	if !foundNPM {
		t.Error("npm package not found")
	}
}

func TestParseCargoDir(t *testing.T) {
	tests := []struct {
		dirname    string
		wantName   string
		wantVer    string
	}{
		{"serde-1.0.163", "serde", "1.0.163"},
		{"tokio-1.28.0", "tokio", "1.28.0"},
	}

	for _, tt := range tests {
		name, ver := parseCargoDir(tt.dirname)
		if name != tt.wantName || ver != tt.wantVer {
			t.Errorf("parseCargoDir(%q) = %q, %q; want %q, %q", tt.dirname, name, ver, tt.wantName, tt.wantVer)
		}
	}
}
