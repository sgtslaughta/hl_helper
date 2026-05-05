package power

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

type fakeRunner struct {
	last []string
	err  error
}

func (f *fakeRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	f.last = append([]string{name}, args...)
	return []byte("ok"), f.err
}

func TestRebootRequiresConfirm(t *testing.T) {
	m := &Manager{R: &fakeRunner{}}
	_, err := m.Apply(context.Background(), Request{Op: OpReboot})
	if !errors.Is(err, ErrNotConfirmed) {
		t.Fatalf("want ErrNotConfirmed, got %v", err)
	}
}

func TestRebootImmediate(t *testing.T) {
	r := &fakeRunner{}
	m := &Manager{R: r}
	res, err := m.Apply(context.Background(), Request{Op: OpReboot, Confirm: true})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.Join(r.last, " "), "-r now") {
		t.Fatalf("got %v", r.last)
	}
	if res.Deferred {
		t.Fatal("expected immediate")
	}
}

func TestShutdownDeferredWithReason(t *testing.T) {
	r := &fakeRunner{}
	m := &Manager{R: r}
	res, err := m.Apply(context.Background(), Request{
		Op:      OpShutdown,
		Delay:   5 * time.Minute,
		Reason:  "kernel update",
		Confirm: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	cmd := strings.Join(r.last, " ")
	if !strings.Contains(cmd, "-h +5") || !strings.Contains(cmd, "kernel update") {
		t.Fatalf("got %v", r.last)
	}
	if !res.Deferred {
		t.Fatal("expected deferred")
	}
}

func TestUnknownOp(t *testing.T) {
	m := &Manager{R: &fakeRunner{}}
	if _, err := m.Apply(context.Background(), Request{Op: "halt", Confirm: true}); err == nil {
		t.Fatal("expected error")
	}
}

func TestCancel(t *testing.T) {
	r := &fakeRunner{}
	m := &Manager{R: r}
	if err := m.Cancel(context.Background()); err != nil {
		t.Fatal(err)
	}
	if strings.Join(r.last, " ") != "shutdown -c" {
		t.Fatalf("got %v", r.last)
	}
}
