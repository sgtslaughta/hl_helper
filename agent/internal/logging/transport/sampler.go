package transport

import (
	"math/rand"
	"path/filepath"

	"github.com/hlhelper/hl-agent/internal/logtypes"
)

type CategoryRule struct {
	Category   string  // exact or glob like "plugin.*"
	Level      string  // optional override
	SampleRate float64 // 0.0 - 1.0
	Drop       bool
}

type Sampler struct {
	DefaultRate float64
	Rules       []CategoryRule
	Rng         *rand.Rand // injectable for deterministic tests
}

// Keep returns true if the event should be retained.
// Always keeps error/critical regardless of rate.
func (s *Sampler) Keep(ev logtypes.Event) bool {
	// Always keep error and critical
	if ev.Log.Level == "error" || ev.Log.Level == "critical" {
		return true
	}

	// Find the first matching rule by category
	category := ""
	if len(ev.Event.Category) > 0 {
		category = ev.Event.Category[0]
	}

	rate := s.DefaultRate
	for _, rule := range s.Rules {
		if globMatch(rule.Category, category) {
			if rule.Drop {
				return false
			}
			rate = rule.SampleRate
			break
		}
	}

	if s.Rng == nil {
		// Fallback to global rand if not injected
		return rand.Float64() < rate
	}
	return s.Rng.Float64() < rate
}

// globMatch checks if a glob pattern matches a string.
// Uses filepath.Match for simplicity.
func globMatch(pattern, s string) bool {
	// filepath.Match requires the string to match the entire pattern.
	// We want "plugin.*" to match "plugin.docker".
	matched, err := filepath.Match(pattern, s)
	return err == nil && matched
}
