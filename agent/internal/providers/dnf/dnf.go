// Package dnf implements providers.Provider for Fedora/RHEL family.
package dnf

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

func (Provider) Name() string { return "dnf" }

func (p *Provider) Detect(ctx context.Context) (bool, error) {
	_, err := p.R.Run(ctx, nil, "dnf", "--version")
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

func (p *Provider) CheckUpdates(ctx context.Context) ([]providers.Update, error) {
	// dnf check-update exits 100 when updates are available -- ignore that
	// specific signal and parse stdout regardless of exit code.
	out, _ := p.R.Run(ctx, nil, "dnf", "-q", "check-update")
	var ups []providers.Update
	sc := bufio.NewScanner(strings.NewReader(string(out)))
	for sc.Scan() {
		line := sc.Text()
		if line == "" || strings.HasPrefix(line, "Obsoleting") || strings.HasPrefix(line, "Last") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 3 {
			continue
		}
		// name.arch  version-release  repo
		nameArch := fields[0]
		dot := strings.LastIndex(nameArch, ".")
		name := nameArch
		if dot > 0 {
			name = nameArch[:dot]
		}
		security := strings.Contains(strings.ToLower(fields[2]), "security")
		ups = append(ups, providers.Update{Name: name, To: fields[1], Security: security})
	}
	return ups, nil
}

func (p *Provider) Apply(ctx context.Context, pkgs []string, opts providers.ApplyOpts) (*providers.ApplyResult, error) {
	if len(pkgs) == 0 {
		return nil, errors.New("dnf: no packages to apply")
	}
	args := []string{"-y", "upgrade"}
	if opts.DryRun {
		args = append([]string{"--setopt=tsflags=test"}, args...)
	}
	args = append(args, pkgs...)
	out, err := p.R.Run(ctx, nil, "dnf", args...)
	txID := fmt.Sprintf("dnf-%d", time.Now().UTC().Unix())
	if hist, herr := p.R.Run(ctx, nil, "dnf", "history", "list", "--reverse"); herr == nil {
		// last line first column is the most recent transaction id
		sc := bufio.NewScanner(strings.NewReader(string(hist)))
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" || strings.HasPrefix(line, "ID") || strings.HasPrefix(line, "-") {
				continue
			}
			fields := strings.Fields(line)
			if len(fields) > 0 {
				txID = "dnf-" + fields[0]
				break
			}
		}
	}
	res := &providers.ApplyResult{TxID: txID, Updated: pkgs}
	if err != nil {
		res.Failed = pkgs
		res.Updated = nil
		return res, fmt.Errorf("dnf upgrade failed: %w: %s", err, string(out))
	}
	return res, nil
}

// Rollback uses `dnf history undo <id>` where id is the numeric portion of TxID.
func (p *Provider) Rollback(ctx context.Context, txID string) error {
	id := strings.TrimPrefix(txID, "dnf-")
	if id == txID {
		return fmt.Errorf("dnf: invalid txID %q", txID)
	}
	if _, err := p.R.Run(ctx, nil, "dnf", "-y", "history", "undo", id); err != nil {
		return fmt.Errorf("dnf history undo %s: %w", id, err)
	}
	return nil
}
