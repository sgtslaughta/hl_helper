# Keystore Package

The `keystore` package provides abstractions for storing and using cryptographic keys.

## Implementations

### FileKeystore

`FileKeystore` stores all keys on disk under a single directory with strict file-mode enforcement:
- Private keys: mode 0600
- Public keys and certificates: mode 0644

**File layout:**
- `signing.key` — Ed25519 private key (PKCS8 PEM)
- `signing.pub` — Ed25519 public key (PKIX PEM)
- `tls.key` — ECDSA P-256 TLS private key (PKCS8 PEM)
- `tls.crt` — TLS leaf certificate (PEM)
- `intermediate.crt` — Intermediate CA certificate (PEM)
- `root.crt` — Root CA certificate (PEM)

### TPMKeystore

`TPMKeystore` stores the Ed25519 signing key inside a TPM 2.0 device, while delegating TLS material to a wrapped `FileKeystore`.

**Rationale:** TPM-resident keys provide better security for signature operations. TLS material remains file-based because `grpcio` uses BoringSSL which cannot directly consume TPM-resident keys.

**File layout (extends FileKeystore):**
- `tpm-handle.bin` — uint32 big-endian persistent handle assigned by TPM (e.g., 0x81010001)
- `tpm-pub.pem` — cached Ed25519 public key (PKIX PEM)
- `tpm-signing.key` — cached signing key (PKCS8 PEM)
- `tls.key`, `tls.crt`, `intermediate.crt`, `root.crt` — managed by inner `FileKeystore`

## Testing with swtpm

TPM tests use `swtpm` (software TPM simulator) for testing:

```bash
# Install swtpm (Ubuntu/Debian)
sudo apt install swtpm

# Run TPM tests
go test ./internal/keystore/... -v -run TPM
```

If `swtpm` is not available, TPM tests skip cleanly with an informative message.

## Interface

Both implementations satisfy the `Keystore` interface:

```go
type Keystore interface {
	GenerateSigning() error
	GenerateTLS() error
	SigningPub() ed25519.PublicKey
	Sign(msg []byte) ([]byte, error)
	TLSCertAndKey() (certChainPEM []byte, keyPEM []byte, err error)
	RootCAPEM() ([]byte, error)
	StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM []byte) error
}
```
