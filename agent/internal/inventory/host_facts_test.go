package inventory

import (
	"strings"
	"testing"
)

func TestParseSSHDConfig(t *testing.T) {
	input := `# This is a comment
Port 22
PermitRootLogin no
  ListenAddress 0.0.0.0
# Another comment
PermitRootLogin yes

PubkeyAuthentication yes
`

	cfg := parseSSHDConfig(strings.NewReader(input))

	tests := []struct {
		key  string
		want string
	}{
		{"port", "22"},
		{"permitrootlogin", "yes"}, // last-wins
		{"listenaddress", "0.0.0.0"},
		{"pubkeyauthentication", "yes"},
	}

	for _, tt := range tests {
		got := cfg[tt.key]
		if got != tt.want {
			t.Errorf("cfg[%q] = %q, want %q", tt.key, got, tt.want)
		}
	}

	// Ensure comment line was skipped
	if _, found := cfg["this"]; found {
		t.Error("comment line should not be parsed")
	}
}

func TestReadLines(t *testing.T) {
	input := "line1\nline2\nline3"
	lines := readLines(strings.NewReader(input))

	if len(lines) != 3 {
		t.Errorf("got %d lines, want 3", len(lines))
	}

	if lines[0] != "line1" || lines[1] != "line2" || lines[2] != "line3" {
		t.Errorf("unexpected lines: %v", lines)
	}
}
