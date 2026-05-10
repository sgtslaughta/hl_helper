package exposure

import (
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

const (
	DefaultMaxProcesses     = 1000
	DefaultMaxConnections   = 5000
	DefaultMaxUniqueLibs    = 10000
	DefaultMaxListeners     = 5000
	DefaultMaxKernelModules = 1000
)

func ApplyProcessBudget(in []*pb.Process, cap int) ([]*pb.Process, bool) {
	if len(in) <= cap {
		return in, false
	}
	return in[:cap], true
}

func ApplyListenerBudget(in []*pb.ListeningSocket, cap int) ([]*pb.ListeningSocket, bool) {
	if len(in) <= cap {
		return in, false
	}
	return in[:cap], true
}

func ApplyConnectionBudget(in []*pb.Connection, cap int) ([]*pb.Connection, bool) {
	if len(in) <= cap {
		return in, false
	}
	return in[:cap], true
}

// DedupeLibs returns unique paths up to cap.
func DedupeLibs(libs []string, cap int) ([]string, bool) {
	seen := make(map[string]struct{}, len(libs))
	out := make([]string, 0, len(libs))
	for _, l := range libs {
		if _, ok := seen[l]; ok {
			continue
		}
		seen[l] = struct{}{}
		if len(out) >= cap {
			break
		}
		out = append(out, l)
	}
	truncated := len(libs) > cap || len(out) >= cap
	return out, truncated
}
