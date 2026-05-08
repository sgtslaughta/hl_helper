package service

import (
	"os"
	"testing"
)

func TestDetectWithEnvOverride(t *testing.T) {
	tests := []struct {
		name    string
		envVal  string
		wantErr bool
	}{
		{"systemd override", "systemd", false},
		{"openrc override", "openrc", false},
		{"launchd override", "launchd", false},
		{"sysv override", "sysv", false},
		{"invalid override", "invalid", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			oldEnv := os.Getenv("HL_INIT_SYSTEM")
			defer func() {
				if oldEnv != "" {
					os.Setenv("HL_INIT_SYSTEM", oldEnv)
				} else {
					os.Unsetenv("HL_INIT_SYSTEM")
				}
			}()

			if tt.envVal != "" {
				os.Setenv("HL_INIT_SYSTEM", tt.envVal)
			} else {
				os.Unsetenv("HL_INIT_SYSTEM")
			}

			m, err := Detect()
			if (err != nil) != tt.wantErr {
				t.Fatalf("Detect() error = %v, wantErr %v", err, tt.wantErr)
			}
			if !tt.wantErr && m == nil {
				t.Fatal("Detect() returned nil manager with no error")
			}
			if !tt.wantErr && m.Kind() != tt.envVal {
				t.Errorf("Kind() = %q, want %q", m.Kind(), tt.envVal)
			}
		})
	}
}
