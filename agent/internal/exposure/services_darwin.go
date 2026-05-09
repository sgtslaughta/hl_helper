//go:build darwin

package exposure

import "time"

type SystemdServiceCollector struct{}

func (c *SystemdServiceCollector) Name() string                     { return "services_systemd" }
func (c *SystemdServiceCollector) Collect(_ time.Time) CollectorResult { return CollectorResult{} }
