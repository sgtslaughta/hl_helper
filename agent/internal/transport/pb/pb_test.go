package pb

import (
	"testing"
	"time"
)

func TestCommandEnvelopePayloadDiscriminator(t *testing.T) {
	tests := []struct {
		name     string
		env      *CommandEnvelope
		expected string
	}{
		{
			name: "pkg_update",
			env: &CommandEnvelope{
				PkgUpdate: &PkgUpdate{DryRun: true},
			},
			expected: "pkg_update",
		},
		{
			name: "reboot",
			env: &CommandEnvelope{
				Reboot: &Reboot{DelaySeconds: 10},
			},
			expected: "reboot",
		},
		{
			name: "shell_exec",
			env: &CommandEnvelope{
				ShellExec: &ShellExec{Command: "ls"},
			},
			expected: "shell_exec",
		},
		{
			name: "terminal_open",
			env: &CommandEnvelope{
				TerminalOpen: &TerminalOpen{SessionID: "sess-1"},
			},
			expected: "terminal_open",
		},
		{
			name: "file_transfer",
			env: &CommandEnvelope{
				FileTransfer: &FileTransfer{Dir: 0},
			},
			expected: "file_transfer",
		},
		{
			name: "docker_op",
			env: &CommandEnvelope{
				DockerOp: &DockerOp{Op: "ps"},
			},
			expected: "docker_op",
		},
		{
			name: "get_facts",
			env: &CommandEnvelope{
				GetFacts: &GetFacts{Keys: []string{"os"}},
			},
			expected: "get_facts",
		},
		{
			name: "plugin_invoke",
			env: &CommandEnvelope{
				PluginInvoke: &PluginInvoke{PluginID: "p1"},
			},
			expected: "plugin_invoke",
		},
		{
			name:     "none",
			env:      &CommandEnvelope{},
			expected: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := tt.env.WhichPayload()
			if result != tt.expected {
				t.Errorf("WhichPayload(): got %q, want %q", result, tt.expected)
			}
		})
	}
}

func TestRiskLevelEnum(t *testing.T) {
	if RISK_LOW != 0 || RISK_MED != 1 || RISK_HIGH != 2 {
		t.Errorf("Risk level enum values incorrect")
	}
}

func TestCommandEnvelopeStructure(t *testing.T) {
	now := time.Now()
	fut := now.Add(5 * time.Minute)

	env := &CommandEnvelope{
		CommandID:   "cmd-1",
		HostID:      "host-1",
		Sequence:    42,
		Nonce:       []byte("test-nonce"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        RISK_LOW,
		Capability:  &CapabilityToken{},
		ShellExec:   &ShellExec{Command: "test"},
		Signature:   []byte("sig"),
	}

	if env.CommandID != "cmd-1" {
		t.Error("CommandID not set")
	}
	if env.Sequence != 42 {
		t.Error("Sequence not set")
	}
	if len(env.Nonce) == 0 {
		t.Error("Nonce not set")
	}
	if env.Risk != RISK_LOW {
		t.Error("Risk not set")
	}
}
