package main

import (
	"context"
	"crypto/ed25519"

	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/rotator"
	"github.com/hlhelper/hl-agent/internal/transport"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type rotatorKeystoreAdapter struct {
	keystore.Keystore
}

func (a *rotatorKeystoreAdapter) SigningPub() []byte {
	return a.Keystore.SigningPub()
}

type rotatorTransportAdapter struct {
	client *transport.Client
}

func (a *rotatorTransportAdapter) SendCertRotate(ctx context.Context, csrPEM, signingPubkey []byte, prevSerial string) error {
	return a.client.SendCertRotate(ctx, &pb.CertRotateRequest{
		CsrPem:        csrPEM,
		SigningPubkey: signingPubkey,
		PrevSerial:    prevSerial,
	})
}

func (a *rotatorTransportAdapter) AwaitCertIssue(ctx context.Context) (*rotator.CertIssue, error) {
	select {
	case m := <-a.client.CertIssueCh():
		ci := &rotator.CertIssue{CertChainPEM: m.CertChainPem}
		if m.NotAfter != nil {
			ci.NotAfter = m.NotAfter.AsTime()
		}
		return ci, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

func (a *rotatorTransportAdapter) Reconnect() {
	a.client.Reconnect()
}

type reenrollKSAdapter struct {
	keystore keystore.Keystore
}

func (a *reenrollKSAdapter) SigningPub() ed25519.PublicKey {
	return a.keystore.SigningPub()
}

func (a *reenrollKSAdapter) Sign(msg []byte) ([]byte, error) {
	return a.keystore.Sign(msg)
}

func (a *reenrollKSAdapter) RotateTLS(commonName string) ([]byte, []byte, []byte, error) {
	return a.keystore.RotateTLS(commonName)
}

func (a *reenrollKSAdapter) StageTLS(chainPEM, privPEM []byte) error {
	return a.keystore.StageTLS(chainPEM, privPEM)
}

func (a *reenrollKSAdapter) VerifyStagedTLS() error {
	return a.keystore.VerifyStagedTLS()
}

func (a *reenrollKSAdapter) CommitTLS() error {
	return a.keystore.CommitTLS()
}

func (a *reenrollKSAdapter) RollbackStagedTLS() error {
	return a.keystore.RollbackStagedTLS()
}
