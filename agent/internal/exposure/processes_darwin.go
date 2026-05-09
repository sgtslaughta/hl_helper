//go:build darwin

package exposure

import "time"

type ProcessCollector struct{}

func (c *ProcessCollector) Name() string { return "processes" }
func (c *ProcessCollector) Collect(_ time.Time) CollectorResult {
	// macOS impl deferred — collector returns empty.
	return CollectorResult{}
}
