// Package apt implements the providers.Provider contract for Debian/Ubuntu
// systems via apt-get + dpkg-query.
package apt

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/hlhelper/hl-agent/internal/providers"
)

// Provider is an apt-backed provider.
type Provider struct {
	R providers.Runner
}

// New returns a Provider wired with the production ExecRunner.
func New() *Provider { return &Provider{R: providers.ExecRunner{}} }

// Name returns "apt".
func (Provider) Name() string { return "apt" }

// Detect returns true if apt-get is on PATH.
func (p *Provider) Detect(ctx context.Context) (bool, error) {
	_, err := p.R.Run(ctx, nil, "apt-get", "--version")
	if err != nil {
		return false, nil
	}
	return true, nil
}

// List returns installed packages parsed from dpkg-query.
func (p *Provider) List(ctx context.Context) ([]providers.Package, error) {
	out, err := p.R.Run(ctx, nil, "dpkg-query", "-W", "-f=${Package} ${Version} ${Architecture}\n")
	if err != nil {
		return nil, fmt.Errorf("dpkg-query: %w", err)
	}
	var pkgs []providers.Package
	sc := bufio.NewScanner(strings.NewReader(string(out)))
	for sc.Scan() {
		fields := strings.Fields(sc.Text())
		if len(fields) < 3 {
			continue
		}
		pkgs = append(pkgs, providers.Package{Name: fields[0], Version: fields[1], Arch: fields[2]})
	}
	return pkgs, nil
}

// CheckUpdates parses `apt-get -s upgrade` output for "Inst" lines.
func (p *Provider) CheckUpdates(ctx context.Context) ([]providers.Update, error) {
	out, err := p.R.Run(ctx, nil, "apt-get", "-s", "upgrade")
	if err != nil {
		return nil, fmt.Errorf("apt-get -s upgrade: %w", err)
	}
	var ups []providers.Update
	sc := bufio.NewScanner(strings.NewReader(string(out)))
	for sc.Scan() {
		line := sc.Text()
		if !strings.HasPrefix(line, "Inst ") {
			continue
		}
		// Inst <pkg> [<from>] (<to> <repo> [arch])
		rest := strings.TrimPrefix(line, "Inst ")
		parts := strings.SplitN(rest, " ", 2)
		if len(parts) < 2 {
			continue
		}
		name := parts[0]
		var from, to string
		if i := strings.Index(parts[1], "["); i >= 0 {
			if j := strings.Index(parts[1][i:], "]"); j > 0 {
				from = parts[1][i+1 : i+j]
			}
		}
		if i := strings.Index(parts[1], "("); i >= 0 {
			if j := strings.Index(parts[1][i:], " "); j > 0 {
				to = parts[1][i+1 : i+j]
			}
		}
		security := strings.Contains(parts[1], "security") || strings.Contains(parts[1], "Security")
		ups = append(ups, providers.Update{Name: name, From: from, To: to, Security: security})
	}
	return ups, nil
}

// Apply installs the given packages non-interactively. TxID is the wall-clock
// timestamp; full transaction parsing requires apt-history reading and is
// deferred to a later phase.
func (p *Provider) Apply(ctx context.Context, pkgs []string, opts providers.ApplyOpts) (*providers.ApplyResult, error) {
	if len(pkgs) == 0 {
		return nil, errors.New("apt: no packages to apply")
	}
	args := []string{"install", "-y", "-o", "Dpkg::Options::=--force-confold"}
	if opts.DryRun {
		args = append([]string{"-s"}, args...)
	}
	args = append(args, pkgs...)
	env := map[string]string{"DEBIAN_FRONTEND": "noninteractive"}
	out, err := p.R.Run(ctx, env, "apt-get", args...)
	res := &providers.ApplyResult{
		TxID:    fmt.Sprintf("apt-%d", time.Now().UTC().Unix()),
		Updated: pkgs,
	}
	if err != nil {
		res.Failed = pkgs
		res.Updated = nil
		return res, fmt.Errorf("apt-get install failed: %w: %s", err, string(out))
	}
	return res, nil
}

// Rollback is not yet implemented for apt; would require apt-history snapshot logic.
func (Provider) Rollback(ctx context.Context, txID string) error {
	return fmt.Errorf("apt: %w (txID=%s)", providers.ErrNotSupported, txID)
}
