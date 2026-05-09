package inventory

import (
	"os"
	"testing"
)

func TestParseDpkgStatus(t *testing.T) {
	tests := []struct {
		name    string
		fixture string
		want    int
	}{
		{
			name:    "parses dpkg status with installed filtering",
			fixture: "testdata/dpkg_status",
			want:    3, // bash, vim, curl (removed-pkg filtered out)
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			f, err := os.Open(tt.fixture)
			if err != nil {
				t.Fatalf("failed to open fixture: %v", err)
			}
			defer f.Close()

			pkgs := parseDpkgStatus(f)
			if len(pkgs) != tt.want {
				t.Errorf("got %d packages, want %d", len(pkgs), tt.want)
			}

			// Verify first package has expected fields
			if len(pkgs) > 0 {
				if pkgs[0].Ecosystem != "dpkg" {
					t.Errorf("got ecosystem %q, want dpkg", pkgs[0].Ecosystem)
				}
				if pkgs[0].Name != "bash" {
					t.Errorf("got name %q, want bash", pkgs[0].Name)
				}
				if pkgs[0].Version != "5.1-2+deb11u1" {
					t.Errorf("got version %q, want 5.1-2+deb11u1", pkgs[0].Version)
				}
				if pkgs[0].Arch != "amd64" {
					t.Errorf("got arch %q, want amd64", pkgs[0].Arch)
				}
			}
		})
	}
}

