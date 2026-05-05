package dnf

import (
	"context"
	"testing"

	"github.com/hlhelper/hl-agent/internal/providers"
)

type fakeRunner struct {
	out map[string][]byte
}

func (f fakeRunner) Run(ctx context.Context, env map[string]string, name string, args ...string) ([]byte, error) {
	key := name
	if len(args) > 0 {
		key = name + " " + args[0]
	}
	return f.out[key], nil
}

func TestList(t *testing.T) {
	out := []byte("bash 5.1.8-3.el9 x86_64\ncurl 7.76.1-19.el9 x86_64\n")
	p := &Provider{R: fakeRunner{out: map[string][]byte{"rpm -qa": out}}}
	pkgs, err := p.List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(pkgs) != 2 || pkgs[1].Name != "curl" {
		t.Fatalf("got %+v", pkgs)
	}
}

func TestCheckUpdates(t *testing.T) {
	out := []byte("\nbash.x86_64  5.1.8-4.el9  baseos\nkernel.x86_64  5.14.0-200  rhel-security\n")
	p := &Provider{R: fakeRunner{out: map[string][]byte{"dnf -q": out}}}
	ups, err := p.CheckUpdates(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(ups) != 2 {
		t.Fatalf("got %+v", ups)
	}
	if !ups[1].Security {
		t.Errorf("kernel should be security")
	}
}

func TestRollbackInvalid(t *testing.T) {
	p := New()
	if err := p.Rollback(context.Background(), "garbage"); err == nil {
		t.Fatal("expected error")
	}
}

func TestApplyEmpty(t *testing.T) {
	if _, err := New().Apply(context.Background(), nil, providers.ApplyOpts{}); err == nil {
		t.Fatal("want error")
	}
}
