package docker

import (
	"context"
	"fmt"
	"strconv"
)

// LifecycleOpts tunes lifecycle calls.
type LifecycleOpts struct {
	Force         bool // bypass managed-label check
	StopTimeoutS  int  // graceful seconds before SIGKILL
	RemoveVolumes bool
}

func (c *Client) ensureManaged(ctx context.Context, id string, force bool) error {
	if force {
		return nil
	}
	out, err := c.run(ctx, "inspect", "--format", "{{index .Config.Labels \"hl_helper.managed\"}}", id)
	if err != nil {
		return err
	}
	if v := string(stripNL(out)); v != "true" {
		return fmt.Errorf("%w: %s", ErrNotManaged, id)
	}
	return nil
}

// Start a container by id or name.
func (c *Client) Start(ctx context.Context, id string, opts LifecycleOpts) error {
	if err := c.ensureManaged(ctx, id, opts.Force); err != nil {
		return err
	}
	_, err := c.run(ctx, "start", id)
	return err
}

// Stop with grace period.
func (c *Client) Stop(ctx context.Context, id string, opts LifecycleOpts) error {
	if err := c.ensureManaged(ctx, id, opts.Force); err != nil {
		return err
	}
	args := []string{"stop"}
	if opts.StopTimeoutS > 0 {
		args = append(args, "-t", strconv.Itoa(opts.StopTimeoutS))
	}
	args = append(args, id)
	_, err := c.run(ctx, args...)
	return err
}

func (c *Client) Restart(ctx context.Context, id string, opts LifecycleOpts) error {
	if err := c.ensureManaged(ctx, id, opts.Force); err != nil {
		return err
	}
	args := []string{"restart"}
	if opts.StopTimeoutS > 0 {
		args = append(args, "-t", strconv.Itoa(opts.StopTimeoutS))
	}
	args = append(args, id)
	_, err := c.run(ctx, args...)
	return err
}

func (c *Client) Remove(ctx context.Context, id string, opts LifecycleOpts) error {
	if err := c.ensureManaged(ctx, id, opts.Force); err != nil {
		return err
	}
	args := []string{"rm", "-f"}
	if opts.RemoveVolumes {
		args = append(args, "-v")
	}
	args = append(args, id)
	_, err := c.run(ctx, args...)
	return err
}

func stripNL(b []byte) []byte {
	for len(b) > 0 && (b[len(b)-1] == '\n' || b[len(b)-1] == '\r' || b[len(b)-1] == ' ') {
		b = b[:len(b)-1]
	}
	return b
}
