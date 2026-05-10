package rotator

import (
	"context"
	"errors"
	"math/rand"
	"path/filepath"
	"testing"
	"time"
)

// chaosKS injects faults at random steps.
type chaosKS struct {
	failAt string // "rotate" | "stage" | "verify" | "commit" | ""
	fakeKS
}

func (k *chaosKS) RotateTLS(cn string) ([]byte, []byte, []byte, error) {
	if k.failAt == "rotate" {
		return nil, nil, nil, errors.New("chaos: rotate")
	}
	return k.fakeKS.RotateTLS(cn)
}

func (k *chaosKS) StageTLS(c, p []byte) error {
	if k.failAt == "stage" {
		return errors.New("chaos: stage")
	}
	return k.fakeKS.StageTLS(c, p)
}

func (k *chaosKS) VerifyStagedTLS() error {
	if k.failAt == "verify" {
		return errors.New("chaos: verify")
	}
	return k.fakeKS.VerifyStagedTLS()
}

func (k *chaosKS) CommitTLS() error {
	if k.failAt == "commit" {
		return errors.New("chaos: commit")
	}
	return k.fakeKS.CommitTLS()
}

func TestRotatorChaosInvariants(t *testing.T) {
	rng := rand.New(rand.NewSource(42))
	steps := []string{"", "rotate", "stage", "verify", "commit"}

	for i := 0; i < 200; i++ {
		failAt := steps[rng.Intn(len(steps))]
		statePath := filepath.Join(t.TempDir(), "s.json")
		tp := &fakeTransport{issueCh: make(chan *CertIssue, 1)}
		tp.issueCh <- &CertIssue{CertChainPEM: []byte("CHAIN")}
		ks := &chaosKS{failAt: failAt, fakeKS: fakeKS{verifyOK: true}}

		r := New(Config{
			HostID:       "h-1",
			Transport:    tp,
			Keystore:     ks,
			StatePath:    statePath,
			PrevSerialFn: func() (string, error) { return "OLD", nil },
		})

		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		_ = r.RotateOnce(ctx)
		cancel()

		st, _ := LoadState(statePath)

		// Invariant 1: phase is one of the documented values
		switch st.Phase {
		case StateNormal, StateRotating, StateRotateBackoff, StateRecovering, StateHalted:
		default:
			t.Errorf("iter %d failAt=%q invalid phase %q", i, failAt, st.Phase)
		}

		// Invariant 2: if commit succeeded (failAt != "commit" + happy path), reconnect was called
		if failAt == "" {
			if tp.reconn != 1 {
				t.Errorf("iter %d: expected reconnect on success, got %d", i, tp.reconn)
			}
		}

		// Invariant 3: never reconnect on failure before commit
		if failAt == "rotate" || failAt == "stage" || failAt == "verify" {
			if tp.reconn != 0 {
				t.Errorf("iter %d failAt=%q: reconnected before commit", i, failAt)
			}
		}
	}
}
