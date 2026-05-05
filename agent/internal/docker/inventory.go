package docker

import (
	"bufio"
	"context"
	"encoding/json"
	"strings"
)

// ListContainers returns running + stopped containers (docker ps -a).
// Output is parsed from `docker ps --format json` line-delimited JSON.
func (c *Client) ListContainers(ctx context.Context) ([]Container, error) {
	out, err := c.run(ctx, "ps", "-a", "--no-trunc", "--format", "{{json .}}")
	if err != nil {
		return nil, err
	}
	var cts []Container
	sc := bufio.NewScanner(strings.NewReader(string(out)))
	sc.Buffer(make([]byte, 0, 64*1024), 1<<20)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		// docker ps --format json keys are different from inspect; map manually.
		var raw struct {
			ID, Image, Names, State, Status, Ports, CreatedAt, Labels string
		}
		if err := json.Unmarshal(line, &raw); err != nil {
			continue
		}
		labels := map[string]string{}
		for _, kv := range strings.Split(raw.Labels, ",") {
			if i := strings.Index(kv, "="); i > 0 {
				labels[strings.TrimSpace(kv[:i])] = strings.TrimSpace(kv[i+1:])
			}
		}
		cts = append(cts, Container{
			ID:      raw.ID,
			Name:    raw.Names,
			Image:   raw.Image,
			State:   raw.State,
			Status:  raw.Status,
			Labels:  labels,
			Ports:   splitPorts(raw.Ports),
			Created: raw.CreatedAt,
		})
	}
	return cts, nil
}

func splitPorts(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	for i, p := range parts {
		parts[i] = strings.TrimSpace(p)
	}
	return parts
}

// Inspect returns the raw inspect json for a single container.
func (c *Client) Inspect(ctx context.Context, id string) (map[string]any, error) {
	out, err := c.run(ctx, "inspect", id)
	if err != nil {
		return nil, err
	}
	var arr []map[string]any
	if err := json.Unmarshal(out, &arr); err != nil {
		return nil, err
	}
	if len(arr) == 0 {
		return nil, nil
	}
	return arr[0], nil
}
