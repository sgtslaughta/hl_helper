package service

import (
	"strings"
	"testing"
)

func TestRenderSystemdTemplate(t *testing.T) {
	u := Unit{
		Name:        "test-agent",
		Description: "Test Agent Service",
		ExecPath:    "/usr/local/bin/test-agent",
		ExecArgs:    []string{"run", "--dir", "/var/lib/test"},
		User:        "testuser",
		Environment: map[string]string{
			"LOG_LEVEL": "debug",
			"DATA_DIR":  "/data",
		},
	}

	content, err := renderSystemd(u)
	if err != nil {
		t.Fatalf("renderSystemd() error = %v", err)
	}

	checks := []string{
		"Description=Test Agent Service",
		"ExecStart=/usr/local/bin/test-agent run --dir /var/lib/test",
		"User=testuser",
		"Environment=",
		"WantedBy=multi-user.target",
	}

	for _, check := range checks {
		if !strings.Contains(content, check) {
			t.Errorf("rendered template missing: %q", check)
		}
	}
}

func TestRenderOpenrcTemplate(t *testing.T) {
	u := Unit{
		Name:        "test-agent",
		Description: "Test Agent Service",
		ExecPath:    "/usr/local/bin/test-agent",
		ExecArgs:    []string{"run", "--dir", "/var/lib/test"},
		User:        "testuser",
		Environment: map[string]string{"LOG_LEVEL": "debug"},
	}

	content, err := renderOpenrc(u)
	if err != nil {
		t.Fatalf("renderOpenrc() error = %v", err)
	}

	checks := []string{
		"description=\"Test Agent Service\"",
		"command=\"/usr/local/bin/test-agent\"",
		"command_user=\"testuser\"",
		"pidfile=\"/run/test-agent.pid\"",
	}

	for _, check := range checks {
		if !strings.Contains(content, check) {
			t.Errorf("rendered template missing: %q", check)
		}
	}
}

func TestRenderSysVTemplate(t *testing.T) {
	u := Unit{
		Name:        "test-agent",
		Description: "Test Agent Service",
		ExecPath:    "/usr/local/bin/test-agent",
		ExecArgs:    []string{"run"},
	}

	content, err := renderSysV(u)
	if err != nil {
		t.Fatalf("renderSysV() error = %v", err)
	}

	checks := []string{
		"Provides:          test-agent",
		"DAEMON=/usr/local/bin/test-agent",
		"start-stop-daemon",
		"pidfile",
	}

	for _, check := range checks {
		if !strings.Contains(content, check) {
			t.Errorf("rendered template missing: %q", check)
		}
	}
}

