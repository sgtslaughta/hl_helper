// Package apk implements providers.Provider for Alpine Linux.
package apk

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

func (Provider) Name() string { return "apk" }

func (p *Provider) Detect(ctx context.Context) (bool, error) {
	_, err := p.R.Run(ctx, nil, "apk", "--version")
	if err != nil {
		return false, nil
	}
	return true, nil
}

func (p *Provider) List(ctx context.Context) ([]providers.Package, error) {
	out, err := p.R.Run(ctx, nil, "apk", "info", "-v")
	if err != nil {
		return nil, fmt.Errorf("apk info: %w", err)
	}
	var pkgs []providers.Package
	sc := bufio.NewScanner(strings.NewReader(string(out)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		// Format: name-version-release  e.g. busybox-1.36.1-r2
		idx := strings.LastIndex(line, "-")
		if idx <= 0 {
			continue
		}
		mid := strings.LastIndex(line[:idx], "-")
		if mid <= 0 {
			continue
		}
		pkgs = append(pkgs, providers.Package{Name: line[:mid], Version: line[mid+1:]})
	}
	return pkgs, nil
}

func (p *Provider) CheckUpdates(ctx context.Context) ([]providers.Update, error) {
	out, err := p.R.Run(ctx, nil, "apk", "version", "-l", "<")
	if err != nil {
		return nil, fmt.Errorf("apk version: %w", err)
	}
	var ups []providers.Update
	sc := bufio.NewScanner(strings.NewReader(string(out)))
	for sc.Scan() {
		line := sc.Text()
		// Lines like: "busybox-1.36.0-r1 < 1.36.1-r2"
		idx := strings.Index(line, "<")
		if idx <= 0 {
			continue
		}
		left := strings.TrimSpace(line[:idx])
		right := strings.TrimSpace(line[idx+1:])
		dash := strings.LastIndex(left, "-")
		if dash <= 0 {
			continue
		}
		mid := strings.LastIndex(left[:dash], "-")
		name := left
		from := ""
		if mid > 0 {
			name = left[:mid]
			from = left[mid+1:]
		}
		ups = append(ups, providers.Update{Name: name, From: from, To: right})
	}
	return ups, nil
}

func (p *Provider) Apply(ctx context.Context, pkgs []string, opts providers.ApplyOpts) (*providers.ApplyResult, error) {
	if len(pkgs) == 0 {
		return nil, errors.New("apk: no packages to apply")
	}
	args := []string{"add", "--upgrade"}
	if opts.DryRun {
		args = append(args, "--simulate")
	}
	args = append(args, pkgs...)
	out, err := p.R.Run(ctx, nil, "apk", args...)
	res := &providers.ApplyResult{
		TxID:    fmt.Sprintf("apk-%d", time.Now().UTC().Unix()),
		Updated: pkgs,
	}
	if err != nil {
		res.Failed = pkgs
		res.Updated = nil
		return res, fmt.Errorf("apk add failed: %w: %s", err, string(out))
	}
	return res, nil
}

func (Provider) Rollback(ctx context.Context, txID string) error {
	return fmt.Errorf("apk: %w (txID=%s)", providers.ErrNotSupported, txID)
}
