package rotator

import (
	"context"
	"fmt"
	"log"
	"time"
)

type Transport interface {
	SendCertRotate(ctx context.Context, csrPEM, signingPubkey []byte, prevSerial string) error
	AwaitCertIssue(ctx context.Context) (*CertIssue, error)
	Reconnect()
}

type CertIssue struct {
	CertChainPEM []byte
	NotAfter     time.Time
}

type KS interface {
	RotateTLS(commonName string) (csrPEM, pubDER, privPEM []byte, err error)
	StageTLS(chainPEM, privPEM []byte) error
	VerifyStagedTLS() error
	CommitTLS() error
	RollbackStagedTLS() error
	SigningPub() []byte
}

type Config struct {
	HostID       string
	Transport    Transport
	Keystore     KS
	StatePath    string
	PrevSerialFn func() (string, error)
	MaxBackoff   time.Duration
	IssueTimeout time.Duration
}

type Rotator struct {
	cfg Config
}

func New(cfg Config) *Rotator {
	if cfg.IssueTimeout == 0 {
		cfg.IssueTimeout = 30 * time.Second
	}
	return &Rotator{cfg: cfg}
}

// RotateOnce performs a single rotation attempt. State persisted at end.
func (r *Rotator) RotateOnce(ctx context.Context) error {
	st, _ := LoadState(r.cfg.StatePath)
	st.Phase = StateRotating
	st.LastAttemptAt = time.Now().UTC()
	_ = SaveState(r.cfg.StatePath, st)

	prevSerial, err := r.cfg.PrevSerialFn()
	if err != nil {
		return r.fail(st, "prev-serial", err)
	}

	csr, _, priv, err := r.cfg.Keystore.RotateTLS(r.cfg.HostID)
	if err != nil {
		return r.fail(st, "rotate-key", err)
	}

	signingPub := r.cfg.Keystore.SigningPub()

	if err := r.cfg.Transport.SendCertRotate(ctx, csr, signingPub, prevSerial); err != nil {
		return r.fail(st, "send", err)
	}

	issueCtx, cancel := context.WithTimeout(ctx, r.cfg.IssueTimeout)
	defer cancel()
	issue, err := r.cfg.Transport.AwaitCertIssue(issueCtx)
	if err != nil {
		return r.fail(st, "await-issue", err)
	}

	if err := r.cfg.Keystore.StageTLS(issue.CertChainPEM, priv); err != nil {
		return r.fail(st, "stage", err)
	}
	if err := r.cfg.Keystore.VerifyStagedTLS(); err != nil {
		_ = r.cfg.Keystore.RollbackStagedTLS()
		return r.fail(st, "verify", err)
	}
	if err := r.cfg.Keystore.CommitTLS(); err != nil {
		return r.fail(st, "commit", err)
	}

	r.cfg.Transport.Reconnect()

	st.Phase = StateNormal
	st.ConsecutiveFailures = 0
	st.HaltedReason = ""
	_ = SaveState(r.cfg.StatePath, st)
	log.Printf("rotator: ok host=%s prev=%s", r.cfg.HostID, prevSerial)
	return nil
}

func (r *Rotator) fail(st State, reason string, cause error) error {
	st.Phase = StateRotateBackoff
	st.ConsecutiveFailures++
	_ = SaveState(r.cfg.StatePath, st)
	return fmt.Errorf("rotate %s: %w", reason, cause)
}
