// Package docker provides container lifecycle management for hl-agent.
// It shells out to the docker CLI (or compatible: podman) so the agent binary
// stays small and avoids cgo. A Runner interface allows mocking in tests.
package docker

import (
	"bytes"
	"context"
	"errors"
	"os/exec"
)

var ErrNotManaged = errors.New("container missing hl_helper.managed=true label")

const ManagedLabel = "hl_helper.managed=true"

// Container is a flattened view of `docker inspect` output.
type Container struct {
	ID       string            `json:"Id"`
	Name     string            `json:"Name"`
	Image    string            `json:"Image"`
	State    string            `json:"State"`
	Status   string            `json:"Status"`
	Labels   map[string]string `json:"Labels"`
	Ports    []string          `json:"Ports"`
	Created  string            `json:"Created"`
	Health   string            `json:"Health,omitempty"`
}

// Image holds image metadata.
type Image struct {
	ID     string `json:"Id"`
	Repo   string `json:"Repo"`
	Tag    string `json:"Tag"`
	Digest string `json:"Digest"`
}

// ApplyResult records the outcome of an update strategy.
type ApplyResult struct {
	TxID     string
	Strategy string
	Before   string // image:digest before
	After    string // image:digest after
	Healthy  bool
}

// Runner abstracts process execution.
type Runner interface {
	Run(ctx context.Context, name string, args ...string) ([]byte, error)
}

// ExecRunner is the default Runner backed by os/exec.
type ExecRunner struct{}

func (ExecRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	if err := cmd.Run(); err != nil {
		return buf.Bytes(), err
	}
	return buf.Bytes(), nil
}
