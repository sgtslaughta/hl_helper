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

// Run is the long-running supervisor: schedules rotation at 50% TTL,
// applies backoff on failure, transitions to RECOVERING when cert expired.
func (r *Rotator) Run(ctx context.Context, certInfoFn func() (notBefore, notAfter time.Time, serial string, err error)) error {
	const (
		minBackoff = 5 * time.Minute
		maxBackoff = 1 * time.Hour
		jitter     = 0.10
	)

	backoff := minBackoff
	for {
		nb, na, _, err := certInfoFn()
		if err != nil {
			log.Printf("rotator: cert info err: %v", err)
			if !sleepCtx(ctx, backoff) {
				return ctx.Err()
			}
			backoff = nextBackoff(backoff, maxBackoff)
			continue
		}

		now := time.Now().UTC()
		if na.Before(now) {
			// Cert expired — recovery path is the supervisor's job, not here.
			log.Printf("rotator: cert expired at %v, deferring to recovery", na)
			if !sleepCtx(ctx, 30*time.Second) {
				return ctx.Err()
			}
			continue
		}

		rotateAt := ComputeRotateAfter(nb, na, now, jitter)
		wait := rotateAt.Sub(now)
		if wait < 0 {
			wait = 0
		}
		log.Printf("rotator: next rotation at %v (wait=%v)", rotateAt, wait)
		if !sleepCtx(ctx, wait) {
			return ctx.Err()
		}

		if err := r.RotateOnce(ctx); err != nil {
			log.Printf("rotator: attempt failed: %v", err)
			if !sleepCtx(ctx, backoff) {
				return ctx.Err()
			}
			backoff = nextBackoff(backoff, maxBackoff)
			continue
		}
		backoff = minBackoff
	}
}

func nextBackoff(cur, max time.Duration) time.Duration {
	next := cur * 2
	if next > max {
		next = max
	}
	return next
}

func sleepCtx(ctx context.Context, d time.Duration) bool {
	if d <= 0 {
		return ctx.Err() == nil
	}
	select {
	case <-time.After(d):
		return true
	case <-ctx.Done():
		return false
	}
}
