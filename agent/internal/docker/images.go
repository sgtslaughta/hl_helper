package docker

import (
	"context"
	"strings"
)

// PullImage fetches image:tag (or @digest).
func (c *Client) PullImage(ctx context.Context, ref string) error {
	_, err := c.run(ctx, "pull", ref)
	return err
}

// ImageDigest returns the canonical content-addressable digest for ref.
// Falls back to RepoDigests if RepoDigest is missing.
func (c *Client) ImageDigest(ctx context.Context, ref string) (string, error) {
	out, err := c.run(ctx, "inspect", "--format", "{{index .RepoDigests 0}}", ref)
	if err != nil {
		return "", err
	}
	d := strings.TrimSpace(string(out))
	// "image@sha256:..." -> return whole thing or split
	if i := strings.Index(d, "@"); i > 0 {
		return d[i+1:], nil
	}
	return d, nil
}

// CosignVerify is a placeholder. Real impl shells out to `cosign verify` with
// configured key + transparency log opts. TODO(C7-phase2).
func (c *Client) CosignVerify(ctx context.Context, ref, keyPath string) error {
	_, err := c.run(ctx, "version") // no-op so call signature is exercised
	if err != nil {
		return err
	}
	// TODO(C7-phase2): integrate cosign verify --key=keyPath ref
	return nil
}
