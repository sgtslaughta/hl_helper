// Package exposure collects runtime exposure data for posture risk weighting.
package exposure

import (
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

// CollectorResult is what each per-OS collector returns. The orchestrator
// merges results from all collectors into a single RuntimeExposure proto.
type CollectorResult struct {
	Processes     []*pb.Process
	Listeners     []*pb.ListeningSocket
	Connections   []*pb.Connection
	Services      []*pb.Service
	KernelModules []*pb.KernelModule
	Containers    []*pb.ContainerExposure
	Truncated     bool
	Errors        []error
}

// Collector is the contract every OS-specific collector implements.
type Collector interface {
	Name() string
	Collect(deadline time.Time) CollectorResult
}
