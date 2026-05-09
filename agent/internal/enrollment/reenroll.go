package enrollment

import (
	"context"
	"crypto/ed25519"
	"fmt"
	"time"
)

// ReenrollServerCaller abstracts the gRPC ReEnroll service for testability.
type ReenrollServerCaller interface {
	Challenge(ctx context.Context, hostID string, signingPubkey []byte) (nonce []byte, err error)
	Complete(ctx context.Context, hostID string, nonce, signature, csrPEM []byte, tsUnix int64) (chainPEM []byte, err error)
}

type ReenrollKS interface {
	SigningPub() ed25519.PublicKey
	Sign(msg []byte) ([]byte, error)
	RotateTLS(commonName string) ([]byte, []byte, []byte, error)
	StageTLS(chainPEM, privPEM []byte) error
	VerifyStagedTLS() error
	CommitTLS() error
	RollbackStagedTLS() error
}

type ReenrollClient struct {
	HostID   string
	Keystore ReenrollKS
	Server   ReenrollServerCaller
}

// Run performs a complete re-enrollment flow.
func (c *ReenrollClient) Run(ctx context.Context) error {
	return c.ReEnroll(ctx)
}

// ReEnroll implements rotator.ReEnroller interface.
func (c *ReenrollClient) ReEnroll(ctx context.Context) error {
	pub := c.Keystore.SigningPub()

	nonce, err := c.Server.Challenge(ctx, c.HostID, pub)
	if err != nil {
		return fmt.Errorf("challenge: %w", err)
	}

	csrPEM, _, privPEM, err := c.Keystore.RotateTLS(c.HostID)
	if err != nil {
		return fmt.Errorf("rotate-tls: %w", err)
	}

	ts := time.Now().UTC().Unix()
	msg := CanonicalReenrollPayload(c.HostID, nonce, ts)
	sig, err := c.Keystore.Sign(msg)
	if err != nil {
		return fmt.Errorf("sign: %w", err)
	}

	chainPEM, err := c.Server.Complete(ctx, c.HostID, nonce, sig, csrPEM, ts)
	if err != nil {
		return fmt.Errorf("complete: %w", err)
	}

	if err := c.Keystore.StageTLS(chainPEM, privPEM); err != nil {
		return fmt.Errorf("stage: %w", err)
	}
	if err := c.Keystore.VerifyStagedTLS(); err != nil {
		_ = c.Keystore.RollbackStagedTLS()
		return fmt.Errorf("verify: %w", err)
	}
	if err := c.Keystore.CommitTLS(); err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	return nil
}
