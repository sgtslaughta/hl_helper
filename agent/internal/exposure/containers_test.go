package exposure

import (
	"testing"
	"time"
)

func TestContainerCollectorReturnsEmptyWhenNoRuntime(t *testing.T) {
	// Without a real Docker/containerd available, collector returns empty
	// CollectorResult and no error fatal.
	c := &ContainerCollector{}
	res := c.Collect(time.Now().Add(time.Second))
	if len(res.Containers) != 0 {
		t.Errorf("expected empty, got %d", len(res.Containers))
	}
}
