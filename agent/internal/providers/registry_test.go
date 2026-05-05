package providers

import (
	"context"
	"errors"
	"testing"
)

type stub struct {
	name string
	on   bool
	err  error
}

func (s *stub) Name() string                                      { return s.name }
func (s *stub) Detect(context.Context) (bool, error)              { return s.on, s.err }
func (s *stub) List(context.Context) ([]Package, error)           { return nil, nil }
func (s *stub) CheckUpdates(context.Context) ([]Update, error)    { return nil, nil }
func (s *stub) Apply(context.Context, []string, ApplyOpts) (*ApplyResult, error) {
	return nil, nil
}
func (s *stub) Rollback(context.Context, string) error { return nil }

func TestRegistryDetectFirstMatch(t *testing.T) {
	r := NewRegistry()
	r.Register(func() Provider { return &stub{name: "a", on: false} })
	r.Register(func() Provider { return &stub{name: "b", on: true} })
	r.Register(func() Provider { return &stub{name: "c", on: true} })
	p, err := r.Detect(context.Background())
	if err != nil || p == nil || p.Name() != "b" {
		t.Fatalf("got %v %v", p, err)
	}
}

func TestRegistryNone(t *testing.T) {
	r := NewRegistry()
	r.Register(func() Provider { return &stub{name: "a", on: false} })
	p, err := r.Detect(context.Background())
	if err != nil || p != nil {
		t.Fatalf("expected nil, got %v %v", p, err)
	}
}

func TestRegistryErrSkip(t *testing.T) {
	r := NewRegistry()
	r.Register(func() Provider { return &stub{name: "a", err: errors.New("boom")} })
	r.Register(func() Provider { return &stub{name: "b", on: true} })
	p, _ := r.Detect(context.Background())
	if p == nil || p.Name() != "b" {
		t.Fatalf("expected b, got %v", p)
	}
}
