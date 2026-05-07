package updater

import (
	"testing"
)

func TestStateRoundTrip(t *testing.T) {
	dir := t.TempDir()
	s := State{
		CurrentVersion:  "0.4.2",
		PreviousVersion: "0.4.1",
		PreviousBinary:  "/var/lib/hl-agent/updates/_prev/hl-agent.prev",
	}
	if err := WriteState(dir, s); err != nil {
		t.Fatal(err)
	}
	got, err := ReadState(dir)
	if err != nil {
		t.Fatal(err)
	}
	if got.CurrentVersion != s.CurrentVersion {
		t.Fatalf("got %+v want %+v", got, s)
	}
}

func TestPendingMarker(t *testing.T) {
	dir := t.TempDir()
	if err := MarkPending(dir, "0.4.3", "/old/bin"); err != nil {
		t.Fatal(err)
	}
	tgt, prev, ok := ReadPending(dir)
	if !ok || tgt != "0.4.3" || prev != "/old/bin" {
		t.Fatalf("pending mismatch: %v %v %v", tgt, prev, ok)
	}
	if err := ClearPending(dir); err != nil {
		t.Fatal(err)
	}
	if _, _, ok := ReadPending(dir); ok {
		t.Fatal("pending should be cleared")
	}
}
