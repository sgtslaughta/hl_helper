//go:build darwin

package exposure

import "time"

type KmodCollector struct{}

func (c *KmodCollector) Name() string                     { return "kernel_modules" }
func (c *KmodCollector) Collect(_ time.Time) CollectorResult { return CollectorResult{} }
