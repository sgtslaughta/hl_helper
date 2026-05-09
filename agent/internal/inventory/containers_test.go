package inventory

import (
	"context"
	"testing"
)

func TestCollectContainersWithoutSocket(t *testing.T) {
	ctx := context.Background()
	containers, err := CollectContainers(ctx)

	// Should return nil/nil when docker socket is missing
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}

	// On test system without docker, should return nil
	if containers != nil && len(containers) > 0 {
		// This is fine, just document the behavior
		t.Logf("found %d containers (docker is available)", len(containers))
	}
}
