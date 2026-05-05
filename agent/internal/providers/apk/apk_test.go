package apk

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
	out := []byte("busybox-1.36.1-r2\nmusl-1.2.4-r0\n")
	p := &Provider{R: fakeRunner{out: map[string][]byte{"apk info": out}}}
	pkgs, err := p.List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(pkgs) != 2 || pkgs[0].Name != "busybox" {
		t.Fatalf("got %+v", pkgs)
	}
}

func TestCheckUpdates(t *testing.T) {
	out := []byte("busybox-1.36.0-r1 < 1.36.1-r2\nmusl-1.2.3-r0 < 1.2.4-r0\n")
	p := &Provider{R: fakeRunner{out: map[string][]byte{"apk version": out}}}
	ups, err := p.CheckUpdates(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(ups) != 2 || ups[0].To != "1.36.1-r2" {
		t.Fatalf("got %+v", ups)
	}
}

func TestRollback(t *testing.T) {
	if err := New().Rollback(context.Background(), "x"); err == nil {
		t.Fatal("want ErrNotSupported")
	}
}

func TestApplyEmpty(t *testing.T) {
	if _, err := New().Apply(context.Background(), nil, providers.ApplyOpts{}); err == nil {
		t.Fatal("want error")
	}
}
