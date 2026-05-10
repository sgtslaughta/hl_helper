package rotator

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"
)

type fakeReenroll struct {
	called int
	err    error
}

func (f *fakeReenroll) ReEnroll(_ context.Context) error {
	f.called++
	return f.err
}

func TestRecoveryNoOpWhenCertHealthy(t *testing.T) {
	now := time.Now().UTC()
	r := NewRecovery(RecoveryConfig{
		StatePath: filepath.Join(t.TempDir(), "s.json"),
		CertInfoFn: func() (time.Time, time.Time, string, error) {
			return now.Add(-1 * time.Hour), now.Add(7 * 24 * time.Hour), "S1", nil
		},
		ReEnroller: &fakeReenroll{},
	})
	if err := r.CheckAndRecover(context.Background()); err != nil {
		t.Fatalf("CheckAndRecover: %v", err)
	}
}

func TestRecoveryTriggersReEnrollOnExpired(t *testing.T) {
	now := time.Now().UTC()
	fr := &fakeReenroll{}
	tp := &fakeTransport{}
	r := NewRecovery(RecoveryConfig{
		StatePath: filepath.Join(t.TempDir(), "s.json"),
		CertInfoFn: func() (time.Time, time.Time, string, error) {
			return now.Add(-2 * time.Hour), now.Add(-1 * time.Hour), "S1", nil
		},
		ReEnroller: fr,
		Transport:  tp,
	})
	if err := r.CheckAndRecover(context.Background()); err != nil {
		t.Fatalf("CheckAndRecover: %v", err)
	}
	if fr.called != 1 {
		t.Errorf("ReEnroll calls = %d, want 1", fr.called)
	}
	if tp.reconn != 1 {
		t.Errorf("Reconnect calls = %d, want 1", tp.reconn)
	}
}

func TestRecoveryHaltsOnPermanentFailure(t *testing.T) {
	now := time.Now().UTC()
	statePath := filepath.Join(t.TempDir(), "s.json")
	r := NewRecovery(RecoveryConfig{
		StatePath: statePath,
		CertInfoFn: func() (time.Time, time.Time, string, error) {
			return now.Add(-2 * time.Hour), now.Add(-1 * time.Hour), "S1", nil
		},
		ReEnroller: &fakeReenroll{err: errors.New("PERMISSION_DENIED: signing_pubkey mismatch")},
		Transport:  &fakeTransport{},
	})
	_ = r.CheckAndRecover(context.Background())
	st, _ := LoadState(statePath)
	if st.Phase != StateHalted {
		t.Errorf("expected HALTED, got %v", st.Phase)
	}
}
