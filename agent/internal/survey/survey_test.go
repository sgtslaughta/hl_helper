package survey_test

import (
	"context"
	"testing"

	"github.com/hlhelper/hl-agent/internal/survey"
)

func TestCollect_BasicShape(t *testing.T) {
	ctx := context.Background()
	s, err := survey.Collect(ctx, "test-host")
	if err != nil {
		t.Fatalf("Collect: %v", err)
	}
	if s == nil {
		t.Fatal("nil survey")
	}
	if s.HostId != "test-host" {
		t.Errorf("HostId = %q, want test-host", s.HostId)
	}
	if s.CollectedAt == nil {
		t.Error("CollectedAt nil")
	}
	if s.Os == "" {
		t.Error("Os empty")
	}
	if s.CpuThreads == 0 {
		t.Error("CpuThreads = 0")
	}
	if s.MemTotalBytes == 0 {
		t.Error("MemTotalBytes = 0")
	}
}
