//go:build darwin

package exposure

import "time"

type SocketCollector struct{}

func (c *SocketCollector) Name() string                     { return "sockets" }
func (c *SocketCollector) Collect(_ time.Time) CollectorResult { return CollectorResult{} }
