package transport

import (
	"math/rand"
	"testing"

	"github.com/hlhelper/hl-agent/internal/logtypes"
)

func makeTestEvent(level string, category string) logtypes.Event {
	return logtypes.Event{
		Log: logtypes.LogFields{
			Level: level,
		},
		Event: logtypes.EventFields{
			Category: []string{category},
		},
	}
}

func TestSamplerKeepsAllAtRate1(t *testing.T) {
	s := &Sampler{
		DefaultRate: 1.0,
		Rng:         rand.New(rand.NewSource(1234)),
	}

	for i := 0; i < 100; i++ {
		ev := makeTestEvent("info", "test")
		if !s.Keep(ev) {
			t.Fatalf("at rate 1.0, expected Keep to return true for event %d", i)
		}
	}
}

func TestSamplerDropsAllAtRate0(t *testing.T) {
	s := &Sampler{
		DefaultRate: 0.0,
		Rng:         rand.New(rand.NewSource(1234)),
	}

	for i := 0; i < 100; i++ {
		ev := makeTestEvent("info", "test")
		if s.Keep(ev) {
			t.Fatalf("at rate 0.0, expected Keep to return false for event %d", i)
		}
	}
}

func TestSamplerAlwaysKeepsErrors(t *testing.T) {
	s := &Sampler{
		DefaultRate: 0.0, // rate is 0, should drop everything
		Rng:         rand.New(rand.NewSource(1234)),
	}

	// error level should always be kept
	ev := makeTestEvent("error", "test")
	if !s.Keep(ev) {
		t.Fatal("expected Keep to return true for error level, even at rate 0.0")
	}

	// critical level should always be kept
	ev = makeTestEvent("critical", "test")
	if !s.Keep(ev) {
		t.Fatal("expected Keep to return true for critical level, even at rate 0.0")
	}

	// info should be dropped
	ev = makeTestEvent("info", "test")
	if s.Keep(ev) {
		t.Fatal("expected Keep to return false for info level at rate 0.0")
	}
}

func TestSamplerCategoryGlobMatch(t *testing.T) {
	s := &Sampler{
		DefaultRate: 0.0,
		Rules: []CategoryRule{
			{
				Category:   "plugin.*",
				SampleRate: 1.0,
			},
		},
		Rng: rand.New(rand.NewSource(1234)),
	}

	// "plugin.docker" matches "plugin.*"
	ev := makeTestEvent("info", "plugin.docker")
	if !s.Keep(ev) {
		t.Fatal("expected glob pattern 'plugin.*' to match 'plugin.docker'")
	}

	// "plugin.kubernetes" matches "plugin.*"
	ev = makeTestEvent("info", "plugin.kubernetes")
	if !s.Keep(ev) {
		t.Fatal("expected glob pattern 'plugin.*' to match 'plugin.kubernetes'")
	}

	// "task" does not match "plugin.*"
	ev = makeTestEvent("info", "task")
	if s.Keep(ev) {
		t.Fatal("expected 'task' not to match 'plugin.*', should use DefaultRate (0.0)")
	}
}

func TestSamplerCategoryExactNotPrefix(t *testing.T) {
	s := &Sampler{
		DefaultRate: 0.0,
		Rules: []CategoryRule{
			{
				Category:   "task",
				SampleRate: 1.0,
			},
		},
		Rng: rand.New(rand.NewSource(1234)),
	}

	// "task" matches "task" exactly
	ev := makeTestEvent("info", "task")
	if !s.Keep(ev) {
		t.Fatal("expected exact category 'task' to match")
	}

	// "task.exec" should NOT match "task" (exact match, not prefix)
	ev = makeTestEvent("info", "task.exec")
	if s.Keep(ev) {
		t.Fatal("expected 'task.exec' not to match exact category 'task'")
	}
}

func TestSamplerDropRuleDiscards(t *testing.T) {
	s := &Sampler{
		DefaultRate: 1.0, // keep all by default
		Rules: []CategoryRule{
			{
				Category: "noise.*",
				Drop:     true,
			},
		},
		Rng: rand.New(rand.NewSource(1234)),
	}

	// "noise.debug" matches "noise.*" with Drop=true
	ev := makeTestEvent("info", "noise.debug")
	if s.Keep(ev) {
		t.Fatal("expected Drop rule to discard 'noise.debug'")
	}

	// "normal.event" doesn't match, uses DefaultRate (1.0)
	ev = makeTestEvent("info", "normal.event")
	if !s.Keep(ev) {
		t.Fatal("expected non-matching event to use DefaultRate (1.0)")
	}
}

func TestSamplerDeterministicWithSeed(t *testing.T) {
	makeSampler := func() *Sampler {
		return &Sampler{
			DefaultRate: 0.5,
			Rng:         rand.New(rand.NewSource(9999)),
		}
	}

	s1 := makeSampler()
	s2 := makeSampler()

	// Both samplers should make the same decisions with same seed
	for i := 0; i < 50; i++ {
		ev := makeTestEvent("info", "test")
		if s1.Keep(ev) != s2.Keep(ev) {
			t.Fatalf("deterministic samplers with same seed should agree at iteration %d", i)
		}
	}
}
