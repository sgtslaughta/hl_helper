//go:build linux

package exposure

import (
	"bufio"
	"os/exec"
	"strings"
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type SystemdServiceCollector struct{}

func (c *SystemdServiceCollector) Name() string { return "services_systemd" }

func (c *SystemdServiceCollector) Collect(deadline time.Time) CollectorResult {
	res := CollectorResult{}
	timeout := time.Until(deadline)
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	out, err := exec.Command("systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend").Output()
	if err != nil {
		// Best-effort: maybe not systemd. Return empty.
		res.Errors = append(res.Errors, err)
		return res
	}
	res.Services = parseSystemctlListUnits(string(out))
	return res
}

func parseSystemctlListUnits(out string) []*pb.Service {
	var services []*pb.Service
	sc := bufio.NewScanner(strings.NewReader(out))
	for sc.Scan() {
		line := sc.Text()
		fields := strings.Fields(line)
		if len(fields) < 4 {
			continue
		}
		// Skip header rows (when --no-legend missing, we still tolerate).
		if fields[0] == "UNIT" {
			continue
		}
		name := fields[0]
		// load active sub ...
		active := fields[2] == "active"
		services = append(services, &pb.Service{
			Name:       name,
			InitSystem: "systemd",
			Active:     active,
			Enabled:    true,  // crude default; refine via `systemctl is-enabled`
		})
	}
	return services
}
