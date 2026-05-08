package tui

import (
	"strings"
	"testing"
	"time"
)

func TestRenderDashboard(t *testing.T) {
	tests := []struct {
		name     string
		snapshot DashboardSnapshot
		contains []string
		notContains []string
	}{
		{
			name: "running and awake",
			snapshot: DashboardSnapshot{
				ServiceState: "running",
				HostID:       "abc123",
				GrpcEndpoint: "fleet.example.com:443",
				AgentVersion: "v0.4.1",
				Hostname:     "laptop-01",
				OS:           "linux",
				OSVersion:    "6.17",
				Arch:         "amd64",
				CertNotAfter: time.Now().Add(90 * 24 * time.Hour),
				Sleeping:     false,
				LastUpdated:  time.Now(),
				Err:          "",
			},
			contains: []string{"HL-AGENT STATUS", "running", "laptop-01", "awake"},
			notContains: []string{"sleeping", "expired"},
		},
		{
			name: "stopped state",
			snapshot: DashboardSnapshot{
				ServiceState: "stopped",
				HostID:       "def456",
				GrpcEndpoint: "fleet.example.com:443",
				AgentVersion: "v0.4.1",
				Hostname:     "laptop-02",
				OS:           "darwin",
				OSVersion:    "14.0",
				Arch:         "arm64",
				CertNotAfter: time.Now().Add(30 * 24 * time.Hour),
				Sleeping:     false,
				LastUpdated:  time.Now(),
				Err:          "",
			},
			contains: []string{"stopped"},
			notContains: []string{"running", "sleeping"},
		},
		{
			name: "sleeping state",
			snapshot: DashboardSnapshot{
				ServiceState: "running",
				HostID:       "ghi789",
				GrpcEndpoint: "fleet.example.com:443",
				AgentVersion: "v0.4.1",
				Hostname:     "laptop-03",
				OS:           "linux",
				OSVersion:    "6.17",
				Arch:         "amd64",
				CertNotAfter: time.Now().Add(60 * 24 * time.Hour),
				Sleeping:     true,
				SleepUntil:   time.Now().Add(2 * time.Hour),
				LastUpdated:  time.Now(),
				Err:          "",
			},
			contains: []string{"sleeping", "until"},
			notContains: []string{"awake"},
		},
		{
			name: "cert expires soon (warning)",
			snapshot: DashboardSnapshot{
				ServiceState: "running",
				HostID:       "jkl012",
				GrpcEndpoint: "fleet.example.com:443",
				AgentVersion: "v0.4.1",
				Hostname:     "laptop-04",
				OS:           "linux",
				OSVersion:    "6.17",
				Arch:         "amd64",
				CertNotAfter: time.Now().Add(3 * 24 * time.Hour), // <7 days
				Sleeping:     false,
				LastUpdated:  time.Now(),
				Err:          "",
			},
			contains: []string{"valid until", "d)"},
			notContains: []string{},
		},
		{
			name: "cert expired",
			snapshot: DashboardSnapshot{
				ServiceState: "running",
				HostID:       "mno345",
				GrpcEndpoint: "fleet.example.com:443",
				AgentVersion: "v0.4.1",
				Hostname:     "laptop-05",
				OS:           "linux",
				OSVersion:    "6.17",
				Arch:         "amd64",
				CertNotAfter: time.Now().Add(-1 * 24 * time.Hour), // expired
				Sleeping:     false,
				LastUpdated:  time.Now(),
				Err:          "",
			},
			contains: []string{"expired"},
			notContains: []string{},
		},
		{
			name: "with error",
			snapshot: DashboardSnapshot{
				ServiceState: "unknown",
				HostID:       "pqr678",
				GrpcEndpoint: "fleet.example.com:443",
				AgentVersion: "v0.4.1",
				Hostname:     "laptop-06",
				OS:           "linux",
				OSVersion:    "6.17",
				Arch:         "amd64",
				CertNotAfter: time.Now().Add(30 * 24 * time.Hour),
				Sleeping:     false,
				LastUpdated:  time.Now(),
				Err:          "connection refused",
			},
			contains: []string{"connection refused"},
			notContains: []string{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			output := render(tt.snapshot)
			for _, want := range tt.contains {
				if !strings.Contains(output, want) {
					t.Errorf("expected to contain %q, got:\n%s", want, output)
				}
			}
			for _, notWant := range tt.notContains {
				if strings.Contains(output, notWant) {
					t.Errorf("expected NOT to contain %q, got:\n%s", notWant, output)
				}
			}
		})
	}
}
