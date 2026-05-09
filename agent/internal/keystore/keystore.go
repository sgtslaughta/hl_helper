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

	// Rotation surface — ALL paths must be safe to call concurrently with
	// transport reads via TLSCertAndKey.

	// RotateTLS generates a fresh ECDSA P-256 keypair and returns
	// (csr_pem, new_pubkey_der, privkey_pem). Does NOT touch on-disk state.
	RotateTLS(commonName string) (csrPEM []byte, pubDER []byte, privPEM []byte, err error)

	// StageTLS writes the new chain + key to staging files (.new suffix).
	// Caller must invoke VerifyStagedTLS then CommitTLS.
	StageTLS(chainPEM, privPEM []byte) error

	// VerifyStagedTLS parses and verifies the staged cert against the pinned
	// root CA, asserting leaf pubkey matches the privkey.
	VerifyStagedTLS() error

	// CommitTLS atomically swaps staged files into place. Old cert is moved to
	// tls.crt.prev for one-cycle rollback. Returns error if staging missing.
	CommitTLS() error

	// RollbackStagedTLS removes staged .new files (used when verify fails).
	RollbackStagedTLS() error
}
