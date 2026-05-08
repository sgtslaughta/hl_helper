package sleep

import (
	"log"
	"time"
)

// Check loads sleep state from stateDir. Returns (sleeping, until).
// Does NOT auto-clear expired sleep state (caller is responsible).
func Check(stateDir string) (bool, time.Time) {
	state, err := Load(stateDir)
	if err != nil {
		log.Printf("sleep: failed to load state: %v", err)
		return false, time.Time{}
	}
	return state.IsSleeping(), state.Until
}
