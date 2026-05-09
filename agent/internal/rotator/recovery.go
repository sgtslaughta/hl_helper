package rotator

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"
)

type ReEnroller interface {
	ReEnroll(ctx context.Context) error
}

type RecoveryConfig struct {
	StatePath  string
	CertInfoFn func() (notBefore, notAfter time.Time, serial string, err error)
	ReEnroller ReEnroller
	Keystore   KS
	Transport  Transport
}

type Recovery struct {
	cfg RecoveryConfig
}

func NewRecovery(cfg RecoveryConfig) *Recovery {
	return &Recovery{cfg: cfg}
}

// CheckAndRecover returns nil if cert healthy, attempts re-enroll if expired.
// Sets HALTED state if re-enroll permanently fails (sig mismatch).
func (r *Recovery) CheckAndRecover(ctx context.Context) error {
	_, notAfter, _, err := r.cfg.CertInfoFn()
	if err != nil {
		// No cert at all — needs full enrollment, not re-enroll.
		return r.haltAt("no-cert", err)
	}
	if notAfter.After(time.Now().UTC()) {
		return nil
	}

	st, _ := LoadState(r.cfg.StatePath)
	st.Phase = StateRecovering
	_ = SaveState(r.cfg.StatePath, st)

	if err := r.cfg.ReEnroller.ReEnroll(ctx); err != nil {
		// Permanent failures (PERMISSION_DENIED) → HALTED
		if isPermanentReEnrollFailure(err) {
			return r.haltAt("reenroll-permanent", err)
		}
		return fmt.Errorf("reenroll: %w", err)
	}

	r.cfg.Transport.Reconnect()
	st.Phase = StateNormal
	st.ConsecutiveFailures = 0
	_ = SaveState(r.cfg.StatePath, st)
	return nil
}

func (r *Recovery) haltAt(reason string, cause error) error {
	st, _ := LoadState(r.cfg.StatePath)
	st.Phase = StateHalted
	st.HaltedReason = fmt.Sprintf("%s: %v", reason, cause)
	_ = SaveState(r.cfg.StatePath, st)
	log.Printf("recovery: halted: %s: %v", reason, cause)
	return fmt.Errorf("halted: %s: %w", reason, cause)
}

func isPermanentReEnrollFailure(err error) bool {
	// Check for grpc PERMISSION_DENIED or NOT_FOUND.
	// Caller must wrap appropriately.
	if err == nil {
		return false
	}
	errStr := err.Error()
	return strings.Contains(errStr, "PERMISSION_DENIED") || strings.Contains(errStr, "NOT_FOUND")
}
