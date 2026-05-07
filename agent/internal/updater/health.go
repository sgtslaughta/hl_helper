package updater

import (
	"fmt"
	"os"
)

type Handler struct {
	StateDir    string
	InstallPath string
}

// ConfirmHealthy is called after gRPC stream + first heartbeat succeed
// on the new binary. Persists state, clears pending marker.
func (h Handler) ConfirmHealthy(newVersion string) error {
	st, _ := ReadState(h.StateDir)
	target, prev, ok := ReadPending(h.StateDir)
	if !ok {
		return nil
	}
	if target != newVersion {
		return fmt.Errorf("pending target %s != running %s", target, newVersion)
	}
	st.PreviousVersion = st.CurrentVersion
	st.PreviousBinary = prev
	st.CurrentVersion = newVersion
	if err := WriteState(h.StateDir, st); err != nil {
		return err
	}
	return ClearPending(h.StateDir)
}

// Rollback swaps the .prev binary back into install path and clears pending.
// Called on second startup after detecting unconfirmed pending.
func (h Handler) Rollback() error {
	_, prev, ok := ReadPending(h.StateDir)
	if !ok {
		return fmt.Errorf("no pending update")
	}
	if _, err := os.Stat(prev); err != nil {
		return fmt.Errorf("prev binary missing: %w", err)
	}
	if err := os.Rename(prev, h.InstallPath); err != nil {
		// Cross-device rename fallback
		if err := copyFile(prev, h.InstallPath); err != nil {
			return err
		}
		_ = os.Remove(prev)
	}
	return ClearPending(h.StateDir)
}
