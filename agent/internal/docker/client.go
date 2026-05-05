package docker

import (
	"context"
	"fmt"
)

// Client wraps a Runner with default args (e.g. --host).
type Client struct {
	R    Runner
	Bin  string   // "docker" or "podman"
	Args []string // global args prepended to every call
}

// NewClient returns a Client backed by the host docker binary.
func NewClient() *Client { return &Client{R: ExecRunner{}, Bin: "docker"} }

// Available returns true if the configured binary responds to `info`.
func (c *Client) Available(ctx context.Context) bool {
	_, err := c.run(ctx, "info", "--format", "{{.ID}}")
	return err == nil
}

func (c *Client) run(ctx context.Context, args ...string) ([]byte, error) {
	all := append([]string{}, c.Args...)
	all = append(all, args...)
	out, err := c.R.Run(ctx, c.Bin, all...)
	if err != nil {
		return out, fmt.Errorf("%s %v: %w (%s)", c.Bin, args, err, string(out))
	}
	return out, nil
}
