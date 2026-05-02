package keystore

import (
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"path/filepath"
)

const (
	// SigningKeyFile is the filename for the Ed25519 signing private key (PKCS8 PEM).
	SigningKeyFile = "signing.key"
	// SigningPubFile is the filename for the Ed25519 signing public key (PKIX PEM).
	SigningPubFile = "signing.pub"
	// TLSKeyFile is the filename for the ECDSA P-256 TLS private key (PKCS8 PEM).
	TLSKeyFile = "tls.key"
	// TLSCertFile is the filename for the TLS certificate (PEM).
	TLSCertFile = "tls.crt"
	// IntermediateFile is the filename for the intermediate CA certificate (PEM).
	IntermediateFile = "intermediate.crt"
	// RootFile is the filename for the root CA certificate (PEM).
	RootFile = "root.crt"
)

// FileKeystore stores agent keys on local disk under a single directory
// with strict file-mode enforcement (0600 for private keys, 0644 for public/certs).
type FileKeystore struct {
	dir        string
	signingKey ed25519.PrivateKey
	signingPub ed25519.PublicKey
}

// OpenFile opens or creates a FileKeystore at dir. The dir must exist;
// missing keys are NOT auto-generated — call Generate* explicitly.
// Existing keys are loaded.
func OpenFile(dir string) (*FileKeystore, error) {
	info, err := os.Stat(dir)
	if err != nil {
		return nil, fmt.Errorf("keystore dir: %w", err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("keystore path is not a directory: %s", dir)
	}
	ks := &FileKeystore{dir: dir}
	if err := ks.loadSigning(); err != nil {
		return nil, err
	}
	return ks, nil
}

func (ks *FileKeystore) GenerateSigning() error {
	if ks.signingKey != nil {
		return nil // idempotent
	}
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return err
	}
	if err := writePrivPKCS8(filepath.Join(ks.dir, SigningKeyFile), priv); err != nil {
		return err
	}
	if err := writePub(filepath.Join(ks.dir, SigningPubFile), pub); err != nil {
		return err
	}
	ks.signingKey = priv
	ks.signingPub = pub
	return nil
}

func (ks *FileKeystore) GenerateTLS() error {
	keyPath := filepath.Join(ks.dir, TLSKeyFile)
	if _, err := os.Stat(keyPath); err == nil {
		return nil // idempotent
	}
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	return writePrivPKCS8(keyPath, priv)
}

func (ks *FileKeystore) loadSigning() error {
	keyPath := filepath.Join(ks.dir, SigningKeyFile)
	data, err := os.ReadFile(keyPath)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	block, _ := pem.Decode(data)
	if block == nil {
		return errors.New("signing.key: bad PEM")
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return err
	}
	priv, ok := parsed.(ed25519.PrivateKey)
	if !ok {
		return errors.New("signing.key: not Ed25519")
	}
	ks.signingKey = priv
	ks.signingPub = priv.Public().(ed25519.PublicKey)
	return nil
}

func (ks *FileKeystore) Dir() string {
	return ks.dir
}

func (ks *FileKeystore) SigningPub() ed25519.PublicKey {
	return ks.signingPub
}

func (ks *FileKeystore) Sign(msg []byte) ([]byte, error) {
	if ks.signingKey == nil {
		return nil, errors.New("signing key not generated")
	}
	return ed25519.Sign(ks.signingKey, msg), nil
}

func (ks *FileKeystore) TLSCertAndKey() ([]byte, []byte, error) {
	leaf, err := os.ReadFile(filepath.Join(ks.dir, TLSCertFile))
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil, nil
	}
	if err != nil {
		return nil, nil, err
	}
	intermediate, err := os.ReadFile(filepath.Join(ks.dir, IntermediateFile))
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, nil, err
	}
	key, err := os.ReadFile(filepath.Join(ks.dir, TLSKeyFile))
	if err != nil {
		return nil, nil, err
	}
	chain := append([]byte{}, leaf...)
	if len(intermediate) > 0 {
		chain = append(chain, intermediate...)
	}
	return chain, key, nil
}

func (ks *FileKeystore) RootCAPEM() ([]byte, error) {
	data, err := os.ReadFile(filepath.Join(ks.dir, RootFile))
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}
	return data, err
}

func (ks *FileKeystore) StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM []byte) error {
	if err := writeFile(filepath.Join(ks.dir, TLSCertFile), leafPEM, 0644); err != nil {
		return err
	}
	if err := writeFile(filepath.Join(ks.dir, IntermediateFile), intermediatePEM, 0644); err != nil {
		return err
	}
	if err := writeFile(filepath.Join(ks.dir, RootFile), rootPEM, 0644); err != nil {
		return err
	}
	return nil
}

// --- helpers ---

func writePrivPKCS8(path string, key any) error {
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		return err
	}
	out := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
	return writeFile(path, out, 0600)
}

func writePub(path string, pub any) error {
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		return err
	}
	out := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})
	return writeFile(path, out, 0644)
}

func writeFile(path string, data []byte, mode os.FileMode) error {
	if err := os.WriteFile(path, data, mode); err != nil {
		return err
	}
	return os.Chmod(path, mode)
}
