// Package keystore manages agent persistent keys.
package keystore

import "crypto/ed25519"

// Keystore abstracts the key storage backend (file, TPM2, etc).
type Keystore interface {
	// GenerateSigning creates a new Ed25519 signing key. Idempotent: no-op if already present.
	GenerateSigning() error
	// GenerateTLS creates a new ECDSA P-256 TLS key. Idempotent.
	GenerateTLS() error
	// SigningPub returns the raw 32-byte Ed25519 public key.
	SigningPub() ed25519.PublicKey
	// Sign signs the given message with the signing key.
	Sign(msg []byte) ([]byte, error)
	// TLSCertAndKey returns (cert_chain_pem, key_pem) for use with crypto/tls.
	// cert_chain_pem is leaf + intermediate concatenated. May be empty if not yet enrolled.
	TLSCertAndKey() (certChainPEM []byte, keyPEM []byte, err error)
	// RootCAPEM returns the trust anchor (root.crt) for verifying server certs. May be empty.
	RootCAPEM() ([]byte, error)
	// StoreEnrollmentBundle persists leaf cert + intermediate + root from enrollment.
	StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM []byte) error
}
