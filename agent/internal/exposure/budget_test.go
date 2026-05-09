package exposure

import (
	"testing"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

func TestApplyBudgetTruncatesProcesses(t *testing.T) {
	procs := make([]*pb.Process, 0, 200)
	for i := 0; i < 200; i++ {
		procs = append(procs, &pb.Process{Pid: uint32(i)})
	}
	out, truncated := ApplyProcessBudget(procs, 100)
	if len(out) != 100 {
		t.Errorf("len = %d, want 100", len(out))
	}
	if !truncated {
		t.Error("truncated = false, want true")
	}
}

func TestApplyBudgetNoOpWhenUnderCap(t *testing.T) {
	procs := []*pb.Process{{Pid: 1}, {Pid: 2}}
	out, truncated := ApplyProcessBudget(procs, 100)
	if len(out) != 2 {
		t.Errorf("len = %d, want 2", len(out))
	}
	if truncated {
		t.Error("truncated = true, want false")
	}
}

func TestDedupeLibsCapsAndDedupes(t *testing.T) {
	libs := []string{}
	for i := 0; i < 15000; i++ {
		libs = append(libs, "/lib/lib"+string(rune('a'+(i%26)))+".so")
	}
	out, truncated := DedupeLibs(libs, 10000)
	if len(out) > 10000 {
		t.Errorf("len = %d, want <= 10000", len(out))
	}
	if !truncated {
		t.Error("expected truncated = true with 15k input")
	}
	seen := map[string]bool{}
	for _, l := range out {
		if seen[l] {
			t.Errorf("duplicate in output: %q", l)
		}
		seen[l] = true
	}
}

func TestDedupeLibsRemovesDuplicates(t *testing.T) {
	libs := []string{"/lib/a.so", "/lib/b.so", "/lib/a.so"}
	out, _ := DedupeLibs(libs, 100)
	if len(out) != 2 {
		t.Errorf("len = %d, want 2 (deduped)", len(out))
	}
}
