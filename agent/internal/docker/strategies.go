package docker

import (
	"context"
	"fmt"
	"time"
)

// RecreateOpts parametrizes the simplest update strategy.
type RecreateOpts struct {
	ContainerID string
	NewImage    string
	StopTimeout int
	Force       bool
}

// Recreate is a stop -> remove -> pull -> run cycle.
// Run command must be reproduced from inspect output; for now the caller is
// responsible for passing a `docker run` command via RunArgs.
func (c *Client) Recreate(ctx context.Context, opts RecreateOpts, runArgs []string) (*ApplyResult, error) {
	before, _ := c.ImageDigest(ctx, opts.NewImage)
	if err := c.Stop(ctx, opts.ContainerID, LifecycleOpts{StopTimeoutS: opts.StopTimeout, Force: opts.Force}); err != nil {
		return nil, fmt.Errorf("recreate stop: %w", err)
	}
	if err := c.Remove(ctx, opts.ContainerID, LifecycleOpts{Force: opts.Force}); err != nil {
		return nil, fmt.Errorf("recreate rm: %w", err)
	}
	if err := c.PullImage(ctx, opts.NewImage); err != nil {
		return nil, fmt.Errorf("recreate pull: %w", err)
	}
	after, _ := c.ImageDigest(ctx, opts.NewImage)
	if len(runArgs) > 0 {
		if _, err := c.run(ctx, append([]string{"run"}, runArgs...)...); err != nil {
			return nil, fmt.Errorf("recreate run: %w", err)
		}
	}
	return &ApplyResult{
		TxID:     fmt.Sprintf("docker-%d", time.Now().UTC().Unix()),
		Strategy: "recreate",
		Before:   before,
		After:    after,
	}, nil
}

// Rolling is a placeholder for swarm-style rolling updates. TODO(C7-phase2).
func (c *Client) Rolling(ctx context.Context, _ RecreateOpts) (*ApplyResult, error) {
	return nil, fmt.Errorf("docker rolling: %w", fmt.Errorf("not implemented"))
}
