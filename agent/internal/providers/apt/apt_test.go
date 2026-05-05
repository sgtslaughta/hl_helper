package apt

import (
	"context"
	"testing"

	"github.com/hlhelper/hl-agent/internal/providers"
)

type fakeRunner struct {
	out map[string][]byte
	err map[string]error
}

func (f fakeRunner) Run(ctx context.Context, env map[string]string, name string, args ...string) ([]byte, error) {
	key := name
	if len(args) > 0 {
		key = name + " " + args[0]
	}
	if e, ok := f.err[key]; ok {
		return f.out[key], e
	}
	return f.out[key], nil
}

func TestDetect(t *testing.T) {
	p := &Provider{R: fakeRunner{out: map[string][]byte{"apt-get --version": []byte("apt 2.4")}}}
	ok, err := p.Detect(context.Background())
	if err != nil || !ok {
		t.Fatalf("expected detect=true, got %v %v", ok, err)
	}
}

func TestList(t *testing.T) {
	out := []byte("bash 5.1 amd64\nzsh 5.8 amd64\n\n")
	p := &Provider{R: fakeRunner{out: map[string][]byte{"dpkg-query -W": out}}}
	pkgs, err := p.List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(pkgs) != 2 || pkgs[0].Name != "bash" || pkgs[1].Version != "5.8" {
		t.Fatalf("parse failed: %+v", pkgs)
	}
}

func TestCheckUpdates(t *testing.T) {
	out := []byte("Reading...\nInst bash [5.1] (5.2 ubuntu-security amd64)\nInst zsh [5.8] (5.9 ubuntu amd64)\n")
	p := &Provider{R: fakeRunner{out: map[string][]byte{"apt-get -s": out}}}
	ups, err := p.CheckUpdates(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(ups) != 2 {
		t.Fatalf("expected 2 updates, got %d", len(ups))
	}
	if !ups[0].Security {
		t.Errorf("bash should be flagged security")
	}
}

func TestApplyEmpty(t *testing.T) {
	p := New()
	if _, err := p.Apply(context.Background(), nil, providers.ApplyOpts{}); err == nil {
		t.Fatal("expected error for empty pkg list")
	}
}

func TestRollbackNotSupported(t *testing.T) {
	p := New()
	err := p.Rollback(context.Background(), "x")
	if err == nil {
		t.Fatal("expected ErrNotSupported")
	}
}
