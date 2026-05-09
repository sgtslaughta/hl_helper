package keystore

import (
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
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
	// The leaf cert is bound to the ECDSA P-256 TLS key — server's BoringSSL
	// doesn't advertise Ed25519 in TLS 1.3 sig schemes, so we keep TLS on
	// ECDSA. Ed25519 signing key is used separately for outbox message auth.
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

// RotateTLS generates a fresh ECDSA P-256 keypair and returns the CSR + key.
// Does NOT modify on-disk state; caller stages via StageTLS.
func (ks *FileKeystore) RotateTLS(commonName string) (csrPEM, pubDER, privPEM []byte, err error) {
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("ecdsa gen: %w", err)
	}

	tmpl := x509.CertificateRequest{
		Subject: pkix.Name{CommonName: commonName},
	}
	csrDER, err := x509.CreateCertificateRequest(rand.Reader, &tmpl, priv)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("create csr: %w", err)
	}
	csrPEM = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE REQUEST", Bytes: csrDER})

	pubDER, err = x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("marshal pub: %w", err)
	}

	privDER, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("marshal priv: %w", err)
	}
	privPEM = pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: privDER})

	return csrPEM, pubDER, privPEM, nil
}

// StageTLS writes the new chain + key to staging files (.new suffix).
func (ks *FileKeystore) StageTLS(chainPEM, privPEM []byte) error {
	if err := writeFile(filepath.Join(ks.dir, "tls.crt.new"), chainPEM, 0o600); err != nil {
		return fmt.Errorf("stage chain: %w", err)
	}
	if err := writeFile(filepath.Join(ks.dir, "tls.key.new"), privPEM, 0o600); err != nil {
		return fmt.Errorf("stage key: %w", err)
	}
	if err := fsyncDir(ks.dir); err != nil {
		return fmt.Errorf("fsync dir: %w", err)
	}
	return nil
}

// RollbackStagedTLS removes staged .new files (used when verify fails).
func (ks *FileKeystore) RollbackStagedTLS() error {
	for _, name := range []string{"tls.crt.new", "tls.key.new"} {
		p := filepath.Join(ks.dir, name)
		if err := os.Remove(p); err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("remove %s: %w", name, err)
		}
	}
	return nil
}

// VerifyStagedTLS parses and verifies the staged cert against the pinned root CA.
func (ks *FileKeystore) VerifyStagedTLS() error {
	chainPath := filepath.Join(ks.dir, "tls.crt.new")
	keyPath := filepath.Join(ks.dir, "tls.key.new")

	chainPEM, err := os.ReadFile(chainPath)
	if err != nil {
		return fmt.Errorf("read staged chain: %w", err)
	}
	keyPEM, err := os.ReadFile(keyPath)
	if err != nil {
		return fmt.Errorf("read staged key: %w", err)
	}

	pair, err := tls.X509KeyPair(chainPEM, keyPEM)
	if err != nil {
		return fmt.Errorf("staged chain+key parse: %w", err)
	}
	if len(pair.Certificate) == 0 {
		return errors.New("staged chain empty")
	}
	leaf, err := x509.ParseCertificate(pair.Certificate[0])
	if err != nil {
		return fmt.Errorf("parse leaf: %w", err)
	}

	// Verify leaf pubkey matches private key
	switch leafPub := leaf.PublicKey.(type) {
	case *ecdsa.PublicKey:
		privPub, ok := pair.PrivateKey.(*ecdsa.PrivateKey)
		if !ok {
			return errors.New("staged: priv key is not ecdsa")
		}
		if leafPub.X.Cmp(privPub.X) != 0 || leafPub.Y.Cmp(privPub.Y) != 0 {
			return errors.New("staged: leaf pubkey does not match privkey")
		}
	default:
		return fmt.Errorf("staged: unsupported leaf pubkey type %T", leafPub)
	}

	// Verify chain against pinned root
	rootPEM, err := ks.RootCAPEM()
	if err != nil || len(rootPEM) == 0 {
		return errors.New("no pinned root CA")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(rootPEM) {
		return errors.New("pinned root parse failed")
	}

	intermediates := x509.NewCertPool()
	for _, der := range pair.Certificate[1:] {
		c, err := x509.ParseCertificate(der)
		if err != nil {
			return fmt.Errorf("intermediate parse: %w", err)
		}
		intermediates.AddCert(c)
	}

	opts := x509.VerifyOptions{
		Roots:         roots,
		Intermediates: intermediates,
	}
	if _, err := leaf.Verify(opts); err != nil {
		return fmt.Errorf("staged chain verify: %w", err)
	}
	return nil
}

// CommitTLS atomically swaps staged files into place.
func (ks *FileKeystore) CommitTLS() error {
	chainNew := filepath.Join(ks.dir, "tls.crt.new")
	keyNew := filepath.Join(ks.dir, "tls.key.new")
	chainCur := filepath.Join(ks.dir, "tls.crt")
	keyCur := filepath.Join(ks.dir, "tls.key")
	chainPrev := filepath.Join(ks.dir, "tls.crt.prev")
	keyPrev := filepath.Join(ks.dir, "tls.key.prev")

	for _, p := range []string{chainNew, keyNew} {
		if _, err := os.Stat(p); err != nil {
			return fmt.Errorf("staged file missing %s: %w", p, err)
		}
	}

	// Move current → prev (best-effort; ok if cur missing on first install)
	if _, err := os.Stat(chainCur); err == nil {
		if err := os.Rename(chainCur, chainPrev); err != nil {
			return fmt.Errorf("backup crt: %w", err)
		}
	}
	if _, err := os.Stat(keyCur); err == nil {
		if err := os.Rename(keyCur, keyPrev); err != nil {
			return fmt.Errorf("backup key: %w", err)
		}
	}

	// New → current
	if err := os.Rename(chainNew, chainCur); err != nil {
		return fmt.Errorf("commit crt: %w", err)
	}
	if err := os.Rename(keyNew, keyCur); err != nil {
		return fmt.Errorf("commit key: %w", err)
	}

	if err := fsyncDir(ks.dir); err != nil {
		return fmt.Errorf("fsync dir: %w", err)
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

func fsyncDir(dir string) error {
	d, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}
