package exposure

import (
	"context"
	"sync"
	"time"

	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type Scanner struct {
	HostID     string
	Collectors []Collector
	Timeout    time.Duration
}

func (s *Scanner) Scan(ctx context.Context) *pb.RuntimeExposure {
	deadline := time.Now().Add(s.Timeout)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}

	results := make([]CollectorResult, len(s.Collectors))
	var wg sync.WaitGroup
	for i, c := range s.Collectors {
		wg.Add(1)
		go func(idx int, col Collector) {
			defer wg.Done()
			results[idx] = col.Collect(deadline)
		}(i, c)
	}
	wg.Wait()

	out := &pb.RuntimeExposure{
		HostId:    s.HostID,
		ScannedAt: timestamppb.Now(),
	}
	for _, r := range results {
		out.Processes = append(out.Processes, r.Processes...)
		out.Listeners = append(out.Listeners, r.Listeners...)
		out.Connections = append(out.Connections, r.Connections...)
		out.Services = append(out.Services, r.Services...)
		out.KernelModules = append(out.KernelModules, r.KernelModules...)
		out.ContainerExposure = append(out.ContainerExposure, r.Containers...)
		if r.Truncated {
			out.Truncated = true
		}
	}
	return out
}
