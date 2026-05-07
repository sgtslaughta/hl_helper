package updater

import (
	"os"
	"path/filepath"
	"testing"
)

func TestHandlePending_ConfirmsOnHealthy(t *testing.T) {
	dir := t.TempDir()
	stateDir := filepath.Join(dir, "s")
	install := filepath.Join(dir, "hl-agent")
	os.WriteFile(install, []byte("NEW"), 0o755)
	prev := filepath.Join(dir, "hl-agent.prev")
	os.WriteFile(prev, []byte("OLD"), 0o755)

	MarkPending(stateDir, "0.4.2", prev)

	h := Handler{StateDir: stateDir, InstallPath: install}
	if err := h.ConfirmHealthy("0.4.2"); err != nil {
		t.Fatal(err)
	}
	if _, _, ok := ReadPending(stateDir); ok {
		t.Fatal("pending should be cleared on healthy confirm")
	}
	st, _ := ReadState(stateDir)
	if st.CurrentVersion != "0.4.2" {
		t.Fatalf("current = %s", st.CurrentVersion)
	}
}

func TestHandlePending_RollbackOnFail(t *testing.T) {
	dir := t.TempDir()
	stateDir := filepath.Join(dir, "s")
	install := filepath.Join(dir, "hl-agent")
	os.WriteFile(install, []byte("NEW_BAD"), 0o755)
	prev := filepath.Join(dir, "hl-agent.prev")
	os.WriteFile(prev, []byte("OLD_GOOD"), 0o755)

	MarkPending(stateDir, "0.4.2", prev)

	h := Handler{StateDir: stateDir, InstallPath: install}
	if err := h.Rollback(); err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(install)
	if string(got) != "OLD_GOOD" {
		t.Fatalf("rollback failed: %s", got)
	}
	if _, _, ok := ReadPending(stateDir); ok {
		t.Fatal("pending should be cleared after rollback")
	}
}
