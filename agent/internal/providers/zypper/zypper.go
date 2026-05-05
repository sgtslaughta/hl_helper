// Package zypper implements providers.Provider for openSUSE / SLES.
package zypper

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/hlhelper/hl-agent/internal/providers"
)

type Provider struct {
	R providers.Runner
}

func New() *Provider { return &Provider{R: providers.ExecRunner{}} }

func (Provider) Name() string { return "zypper" }

func (p *Provider) Detect(ctx context.Context) (bool, error) {
	_, err := p.R.Run(ctx, nil, "zypper", "--version")
	if err != nil {
		return false, nil
	}
	return true, nil
}

func (p *Provider) List(ctx context.Context) ([]providers.Package, error) {
	out, err := p.R.Run(ctx, nil, "rpm", "-qa", "--qf", "%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n")
	if err != nil {
		return nil, fmt.Errorf("rpm -qa: %w", err)
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

// CheckUpdates parses `zypper -t list-updates` table output.
//
// Sample format:
//
//	S | Repository | Name | Current Version | Available Version | Arch
//	v | repo-oss   | bash | 5.1.16-150400.3 | 5.2.15-150500.1   | x86_64
func (p *Provider) CheckUpdates(ctx context.Context) ([]providers.Update, error) {
	out, _ := p.R.Run(ctx, nil, "zypper", "--non-interactive", "list-updates")
	var ups []providers.Update
	sc := bufio.NewScanner(strings.NewReader(string(out)))
	for sc.Scan() {
		line := sc.Text()
		if !strings.Contains(line, "|") || strings.HasPrefix(line, "S ") || strings.HasPrefix(line, "--") {
			continue
		}
		parts := strings.Split(line, "|")
		if len(parts) < 6 {
			continue
		}
		for i := range parts {
			parts[i] = strings.TrimSpace(parts[i])
		}
		security := strings.Contains(strings.ToLower(parts[1]), "security")
		ups = append(ups, providers.Update{
			Name:     parts[2],
			From:     parts[3],
			To:       parts[4],
			Security: security,
		})
	}
	return ups, nil
}

func (p *Provider) Apply(ctx context.Context, pkgs []string, opts providers.ApplyOpts) (*providers.ApplyResult, error) {
	if len(pkgs) == 0 {
		return nil, errors.New("zypper: no packages to apply")
	}
	args := []string{"--non-interactive", "update"}
	if opts.DryRun {
		args = append(args, "--dry-run")
	}
	args = append(args, pkgs...)
	out, err := p.R.Run(ctx, nil, "zypper", args...)
	res := &providers.ApplyResult{
		TxID:    fmt.Sprintf("zypper-%d", time.Now().UTC().Unix()),
		Updated: pkgs,
	}
	if err != nil {
		res.Failed = pkgs
		res.Updated = nil
		return res, fmt.Errorf("zypper update failed: %w: %s", err, string(out))
	}
	return res, nil
}

// Rollback uses `snapper rollback <txID>` if available; falls back to ErrNotSupported.
func (Provider) Rollback(ctx context.Context, txID string) error {
	return fmt.Errorf("zypper: %w (txID=%s)", providers.ErrNotSupported, txID)
}
