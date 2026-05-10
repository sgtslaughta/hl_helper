package transport_test

import (
	"testing"

	"github.com/hlhelper/hl-agent/internal/logging/transport"
)

func TestInternReturnsStableID(t *testing.T) {
	d := transport.New()
	id1, isNew1 := d.Intern("task.exec.completed")
	if !isNew1 {
		t.Fatal("first intern should be new")
	}
	id2, isNew2 := d.Intern("task.exec.completed")
	if isNew2 {
		t.Fatal("second intern should not be new")
	}
	if id1 != id2 {
		t.Fatalf("ids diverged: %d != %d", id1, id2)
	}
	if id1 == 0 {
		t.Fatal("id should be non-zero")
	}
}

func TestInternUniqueIDsPerString(t *testing.T) {
	d := transport.New()
	a, _ := d.Intern("x")
	b, _ := d.Intern("y")
	if a == b {
		t.Fatal("different strings must get different ids")
	}
}

func TestVersionBumpsOnNewIntern(t *testing.T) {
	d := transport.New()
	v0 := d.Version()
	d.Intern("a")
	v1 := d.Version()
	if v1 <= v0 {
		t.Fatalf("version did not advance: %d -> %d", v0, v1)
	}
	d.Intern("a") // re-intern same: no bump
	v2 := d.Version()
	if v2 != v1 {
		t.Fatal("re-intern should not advance version")
	}
	d.Intern("b")
	v3 := d.Version()
	if v3 <= v2 {
		t.Fatal("new intern should advance version")
	}
}

func TestSnapshotAndDelta(t *testing.T) {
	d := transport.New()
	d.Intern("a")
	d.Intern("b")
	d.Intern("c")
	snap := d.Snapshot()
	if len(snap) != 3 {
		t.Fatalf("snapshot len: %d", len(snap))
	}
	delta1 := d.Delta()
	if len(delta1) != 3 {
		t.Fatalf("first delta should contain all entries, got %d", len(delta1))
	}
	delta2 := d.Delta()
	if len(delta2) != 0 {
		t.Fatalf("subsequent delta should be empty, got %d", len(delta2))
	}
	d.Intern("d")
	delta3 := d.Delta()
	if len(delta3) != 1 {
		t.Fatalf("delta after one new intern should be 1, got %d", len(delta3))
	}
}

func TestResetClearsState(t *testing.T) {
	d := transport.New()
	d.Intern("a")
	d.Intern("b")
	d.Reset()
	if len(d.Snapshot()) != 0 {
		t.Fatal("snapshot should be empty after Reset")
	}
	if d.Version() != 0 {
		t.Fatal("version should reset to 0")
	}
	id, isNew := d.Intern("a")
	if !isNew {
		t.Fatal("post-reset intern should be new")
	}
	if id == 0 {
		t.Fatal("id should be non-zero")
	}
}

func TestConcurrentInternsAreSafe(t *testing.T) {
	d := transport.New()
	done := make(chan struct{}, 8)
	for i := 0; i < 8; i++ {
		go func(i int) {
			for j := 0; j < 100; j++ {
				d.Intern("shared")
				d.Intern("private")
			}
			done <- struct{}{}
		}(i)
	}
	for i := 0; i < 8; i++ {
		<-done
	}
	if len(d.Snapshot()) != 2 {
		t.Fatalf("expected 2 unique entries, got %d", len(d.Snapshot()))
	}
}
