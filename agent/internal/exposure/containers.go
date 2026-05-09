package exposure

import (
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

// ContainerCollector best-effort enumerates running containers and runs
// process/listener scans inside their PID namespace via nsenter. v1 minimal:
// returns empty if no container runtime detected. Real impl deferred to v2.
type ContainerCollector struct{}

func (c *ContainerCollector) Name() string { return "containers" }

func (c *ContainerCollector) Collect(_ time.Time) CollectorResult {
	res := CollectorResult{}
	// v1 minimal: enumerate via existing inventory/containers, but skip the
	// nsenter inside-container scan (privilege complexity). Mark partial=true
	// for any container we can list but not introspect.
	// (Full impl in follow-up — for now ship empty.)
	_ = pb.ContainerExposure{}
	return res
}
