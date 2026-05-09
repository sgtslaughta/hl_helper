package exposure

import (
	"context"
	"testing"
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type fakeCollector struct {
	name string
	res  CollectorResult
}

func (f *fakeCollector) Name() string                       { return f.name }
func (f *fakeCollector) Collect(_ time.Time) CollectorResult { return f.res }

func TestScannerMergesCollectorResults(t *testing.T) {
	ctx := context.Background()
	c1 := &fakeCollector{name: "procs", res: CollectorResult{
		Processes: []*pb.Process{{Pid: 1, ExePath: "/a"}},
	}}
	c2 := &fakeCollector{name: "socks", res: CollectorResult{
		Listeners: []*pb.ListeningSocket{{Proto: "tcp", Port: 443}},
	}}

	s := &Scanner{Collectors: []Collector{c1, c2}, HostID: "h-1", Timeout: 5 * time.Second}
	out := s.Scan(ctx)
	if out.HostId != "h-1" {
		t.Errorf("HostId = %q, want h-1", out.HostId)
	}
	if len(out.Processes) != 1 || out.Processes[0].ExePath != "/a" {
		t.Errorf("processes merge: %v", out.Processes)
	}
	if len(out.Listeners) != 1 || out.Listeners[0].Port != 443 {
		t.Errorf("listeners merge: %v", out.Listeners)
	}
	if out.ScannedAt == nil || out.ScannedAt.Seconds == 0 {
		t.Error("ScannedAt not populated")
	}
}

func TestScannerPropagatesTruncatedFlag(t *testing.T) {
	ctx := context.Background()
	c := &fakeCollector{res: CollectorResult{Truncated: true}}
	s := &Scanner{Collectors: []Collector{c}, HostID: "h-1", Timeout: time.Second}
	out := s.Scan(ctx)
	if !out.Truncated {
		t.Error("expected Truncated=true")
	}
}
