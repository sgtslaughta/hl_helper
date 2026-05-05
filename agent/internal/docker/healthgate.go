package docker

import (
	"context"
	"strings"
	"time"
)

// WaitHealthy polls inspect.State.Health.Status until "healthy" or timeout.
// Containers without a HEALTHCHECK report Health == "" -- we then fall back
// to State == "running" + an interval.
func (c *Client) WaitHealthy(ctx context.Context, id string, timeout time.Duration) (bool, error) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		out, err := c.run(ctx, "inspect", "--format", "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}", id)
		if err != nil {
			return false, err
		}
		s := strings.TrimSpace(string(out))
		parts := strings.SplitN(s, "|", 2)
		state := parts[0]
		health := ""
		if len(parts) == 2 {
			health = parts[1]
		}
		switch {
		case health == "healthy":
			return true, nil
		case health == "unhealthy":
			return false, nil
		case health == "" && state == "running":
			// no healthcheck defined -- consider running == healthy after stable interval
			time.Sleep(2 * time.Second)
			out2, _ := c.run(ctx, "inspect", "--format", "{{.State.Status}}", id)
			if strings.TrimSpace(string(out2)) == "running" {
				return true, nil
			}
		}
		select {
		case <-ctx.Done():
			return false, ctx.Err()
		case <-time.After(time.Second):
		}
	}
	return false, nil
}
