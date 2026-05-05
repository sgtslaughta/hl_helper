package providers

import (
	"context"
)

// Detector is the function signature used to enumerate available providers.
type Detector func() Provider

// Registry holds an ordered list of provider constructors. The first one whose
// Detect returns (true, nil) wins.
type Registry struct {
	detectors []Detector
}

// NewRegistry returns an empty registry.
func NewRegistry() *Registry { return &Registry{} }

// Register appends a provider constructor.
func (r *Registry) Register(d Detector) { r.detectors = append(r.detectors, d) }

// Detect returns the first matching provider on this host, or nil if none match.
func (r *Registry) Detect(ctx context.Context) (Provider, error) {
	for _, d := range r.detectors {
		p := d()
		ok, err := p.Detect(ctx)
		if err != nil {
			continue
		}
		if ok {
			return p, nil
		}
	}
	return nil, nil
}
