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
	Resolver   Resolver // nil = no enrichment
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

	// Enrich with package information if resolver available
	if s.Resolver != nil {
		paths := uniquePaths(out)
		mapping := s.Resolver.Resolve(paths)
		enrich(out, mapping)
	}

	return out
}

func uniquePaths(r *pb.RuntimeExposure) []string {
	seen := map[string]struct{}{}
	for _, p := range r.Processes {
		if p.ExePath != "" {
			seen[p.ExePath] = struct{}{}
		}
		for _, lib := range p.LoadedLibs {
			seen[lib] = struct{}{}
		}
	}
	for _, s := range r.Services {
		if s.ExecPath != "" {
			seen[s.ExecPath] = struct{}{}
		}
	}
	out := make([]string, 0, len(seen))
	for p := range seen {
		out = append(out, p)
	}
	return out
}

func enrich(r *pb.RuntimeExposure, mapping map[string]PathPkg) {
	for _, p := range r.Processes {
		if v, ok := mapping[p.ExePath]; ok {
			p.Pkg = v.Pkg
			p.PkgVersion = v.Version
		}
	}
	for _, s := range r.Services {
		if v, ok := mapping[s.ExecPath]; ok {
			s.Pkg = v.Pkg
			s.PkgVersion = v.Version
		}
	}
}
