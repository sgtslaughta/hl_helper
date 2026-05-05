package zypper

import (
	"context"
	"testing"

	"github.com/hlhelper/hl-agent/internal/providers"
)

type fakeRunner struct{ out map[string][]byte }

func (f fakeRunner) Run(ctx context.Context, env map[string]string, name string, args ...string) ([]byte, error) {
	key := name
	if len(args) > 0 {
		key = name + " " + args[0]
	}
	return f.out[key], nil
}

func TestList(t *testing.T) {
	out := []byte("bash 5.1.16-150400.3 x86_64\n")
	p := &Provider{R: fakeRunner{out: map[string][]byte{"rpm -qa": out}}}
	pkgs, err := p.List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(pkgs) != 1 || pkgs[0].Name != "bash" {
		t.Fatalf("got %+v", pkgs)
	}
}

func TestCheckUpdatesParse(t *testing.T) {
	out := []byte(`S | Repository | Name | Current Version | Available Version | Arch
--+-----------+------+-----------------+-------------------+-------
v | security  | bash | 5.1.16          | 5.2.15            | x86_64
v | repo-oss  | curl | 7.79.1          | 7.88.0            | x86_64
`)
	p := &Provider{R: fakeRunner{out: map[string][]byte{"zypper --non-interactive": out}}}
	ups, err := p.CheckUpdates(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(ups) != 2 {
		t.Fatalf("got %+v", ups)
	}
	if !ups[0].Security {
		t.Errorf("bash should be security")
	}
}

func TestApplyEmpty(t *testing.T) {
	if _, err := New().Apply(context.Background(), nil, providers.ApplyOpts{}); err == nil {
		t.Fatal("expected error")
	}
}

func TestRollbackUnsupported(t *testing.T) {
	if err := New().Rollback(context.Background(), "x"); err == nil {
		t.Fatal("expected error")
	}
}
