package keystore_test

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"testing"
	"time"

	"go.uber.org/goleak"

	"github.com/hlhelper/hl-agent/internal/keystore"
)

func TestMain(m *testing.M) {
	goleak.VerifyTestMain(m)
}

func TestOpenFileRequiresExistingDir(t *testing.T) {
	_, err := keystore.OpenFile("/nonexistent/path/to/dir")
	if err == nil {
		t.Fatal("expected error for non-existent dir")
	}
}

func TestOpenFileFailsForNonDirectory(t *testing.T) {
	tmpfile, err := os.CreateTemp("", "testfile")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(tmpfile.Name())
	tmpfile.Close()

	_, err = keystore.OpenFile(tmpfile.Name())
	if err == nil {
		t.Fatal("expected error for non-directory path")
	}
}

func TestGenerateSigningCreatesKeyFiles(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateSigning()
	if err != nil {
		t.Fatal(err)
	}

	keyPath := filepath.Join(tmpdir, "signing.key")
	pubPath := filepath.Join(tmpdir, "signing.pub")

	// Check files exist
	info, err := os.Stat(keyPath)
	if err != nil {
		t.Fatalf("signing.key does not exist: %v", err)
	}
	if mode := info.Mode().Perm(); mode != 0600 {
		t.Fatalf("signing.key mode = %o, want 0600", mode)
	}

	info, err = os.Stat(pubPath)
	if err != nil {
		t.Fatalf("signing.pub does not exist: %v", err)
	}
	if mode := info.Mode().Perm(); mode != 0644 {
		t.Fatalf("signing.pub mode = %o, want 0644", mode)
	}
}

func TestGenerateSigningIsIdempotent(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateSigning()
	if err != nil {
		t.Fatal(err)
	}

	pub1 := ks.SigningPub()

	err = ks.GenerateSigning()
	if err != nil {
		t.Fatal(err)
	}

	pub2 := ks.SigningPub()
	if !pub1.Equal(pub2) {
		t.Fatal("public key changed after second GenerateSigning")
	}
}

func TestSignAndVerifyRoundtrip(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateSigning()
	if err != nil {
		t.Fatal(err)
	}

	msg := []byte("test message")
	sig, err := ks.Sign(msg)
	if err != nil {
		t.Fatal(err)
	}

	pubKey := ks.SigningPub()
	if !ed25519.Verify(pubKey, msg, sig) {
		t.Fatal("signature verification failed")
	}
}

func TestSignWithoutGenerateErrors(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	_, err = ks.Sign([]byte("test"))
	if err == nil {
		t.Fatal("expected error when signing without generating key")
	}
}

func TestGenerateTLSCreatesKeyFile(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateTLS()
	if err != nil {
		t.Fatal(err)
	}

	keyPath := filepath.Join(tmpdir, "tls.key")
	info, err := os.Stat(keyPath)
	if err != nil {
		t.Fatalf("tls.key does not exist: %v", err)
	}
	if mode := info.Mode().Perm(); mode != 0600 {
		t.Fatalf("tls.key mode = %o, want 0600", mode)
	}
}

func TestGenerateTLSIsIdempotent(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateTLS()
	if err != nil {
		t.Fatal(err)
	}

	keyPath := filepath.Join(tmpdir, "tls.key")
	data1, err := os.ReadFile(keyPath)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateTLS()
	if err != nil {
		t.Fatal(err)
	}

	data2, err := os.ReadFile(keyPath)
	if err != nil {
		t.Fatal(err)
	}

	if string(data1) != string(data2) {
		t.Fatal("tls.key changed after second GenerateTLS (should be idempotent)")
	}
}

func TestPersistenceAcrossOpens(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateSigning()
	if err != nil {
		t.Fatal(err)
	}

	msg := []byte("test message")
	sig1, err := ks.Sign(msg)
	if err != nil {
		t.Fatal(err)
	}

	pub1 := ks.SigningPub()

	// Re-open the keystore
	ks2, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	pub2 := ks2.SigningPub()
	if !pub1.Equal(pub2) {
		t.Fatal("public key doesn't match after reopening")
	}

	sig2, err := ks2.Sign(msg)
	if err != nil {
		t.Fatal(err)
	}

	if string(sig1) != string(sig2) {
		t.Fatal("signature is not deterministic (Ed25519 should be deterministic)")
	}
}

func TestStoreEnrollmentBundlePersistsCertFiles(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	leafPEM := []byte("LEAF CERT")
	intermediatePEM := []byte("INTERMEDIATE CERT")
	rootPEM := []byte("ROOT CERT")

	err = ks.StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM)
	if err != nil {
		t.Fatal(err)
	}

	// Check tls.crt
	data, err := os.ReadFile(filepath.Join(tmpdir, "tls.crt"))
	if err != nil {
		t.Fatalf("tls.crt not found: %v", err)
	}
	if string(data) != string(leafPEM) {
		t.Fatal("tls.crt content mismatch")
	}
	info, err := os.Stat(filepath.Join(tmpdir, "tls.crt"))
	if mode := info.Mode().Perm(); mode != 0644 {
		t.Fatalf("tls.crt mode = %o, want 0644", mode)
	}

	// Check intermediate.crt
	data, err = os.ReadFile(filepath.Join(tmpdir, "intermediate.crt"))
	if err != nil {
		t.Fatalf("intermediate.crt not found: %v", err)
	}
	if string(data) != string(intermediatePEM) {
		t.Fatal("intermediate.crt content mismatch")
	}
	info, err = os.Stat(filepath.Join(tmpdir, "intermediate.crt"))
	if mode := info.Mode().Perm(); mode != 0644 {
		t.Fatalf("intermediate.crt mode = %o, want 0644", mode)
	}

	// Check root.crt
	data, err = os.ReadFile(filepath.Join(tmpdir, "root.crt"))
	if err != nil {
		t.Fatalf("root.crt not found: %v", err)
	}
	if string(data) != string(rootPEM) {
		t.Fatal("root.crt content mismatch")
	}
	info, err = os.Stat(filepath.Join(tmpdir, "root.crt"))
	if mode := info.Mode().Perm(); mode != 0644 {
		t.Fatalf("root.crt mode = %o, want 0644", mode)
	}
}

func TestTLSCertAndKeyConcatenatesLeafAndIntermediate(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	// Leaf cert is bound to the ECDSA TLS key (server BoringSSL doesn't
	// advertise Ed25519 sig schemes), so TLSCertAndKey returns tls.key.
	err = ks.GenerateTLS()
	if err != nil {
		t.Fatal(err)
	}

	leafPEM := []byte("LEAF CERT")
	intermediatePEM := []byte("INTERMEDIATE CERT")
	rootPEM := []byte("ROOT CERT")

	err = ks.StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM)
	if err != nil {
		t.Fatal(err)
	}

	certChain, keyPEM, err := ks.TLSCertAndKey()
	if err != nil {
		t.Fatal(err)
	}

	// Check concatenation
	expectedChain := append([]byte{}, leafPEM...)
	expectedChain = append(expectedChain, intermediatePEM...)

	if string(certChain) != string(expectedChain) {
		t.Fatalf("cert chain mismatch:\ngot:  %q\nwant: %q", string(certChain), string(expectedChain))
	}

	// Check key matches tls.key (ECDSA, paired with the leaf cert)
	tlsKeyData, err := os.ReadFile(filepath.Join(tmpdir, "tls.key"))
	if err != nil {
		t.Fatal(err)
	}
	if string(keyPEM) != string(tlsKeyData) {
		t.Fatal("keyPEM does not match tls.key content")
	}
}

func TestTLSCertAndKeyReturnsNilWhenNotEnrolled(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	err = ks.GenerateTLS()
	if err != nil {
		t.Fatal(err)
	}

	certChain, keyPEM, err := ks.TLSCertAndKey()
	if err != nil {
		t.Fatal(err)
	}
	if certChain != nil {
		t.Fatalf("expected nil cert chain when not enrolled, got %v", certChain)
	}
	if keyPEM != nil {
		t.Fatalf("expected nil keyPEM when not enrolled, got %v", keyPEM)
	}
}

func TestRootCAPEMReturnsBytesAfterStore(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	rootPEM := []byte("ROOT CERT PEM")
	err = ks.StoreEnrollmentBundle([]byte("LEAF"), []byte("INTERMEDIATE"), rootPEM)
	if err != nil {
		t.Fatal(err)
	}

	data, err := ks.RootCAPEM()
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != string(rootPEM) {
		t.Fatal("RootCAPEM content mismatch")
	}
}

func TestRootCAPEMReturnsNilNilWhenAbsent(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	data, err := ks.RootCAPEM()
	if err != nil {
		t.Fatal(err)
	}
	if data != nil {
		t.Fatalf("expected nil data when root.crt absent, got %v", data)
	}
}

func TestRotateTLSGeneratesFreshKeypair(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}
	if err := ks.GenerateSigning(); err != nil {
		t.Fatalf("GenerateSigning: %v", err)
	}
	if err := ks.GenerateTLS(); err != nil {
		t.Fatalf("GenerateTLS: %v", err)
	}

	csr1, pub1, priv1, err := ks.RotateTLS("h-1")
	if err != nil {
		t.Fatalf("RotateTLS: %v", err)
	}
	if len(csr1) == 0 || len(pub1) == 0 || len(priv1) == 0 {
		t.Fatal("expected non-empty outputs")
	}

	csr2, pub2, _, err := ks.RotateTLS("h-1")
	if err != nil {
		t.Fatalf("RotateTLS#2: %v", err)
	}
	if bytes.Equal(pub1, pub2) {
		t.Fatal("expected distinct keypairs")
	}
	if bytes.Equal(csr1, csr2) {
		t.Fatal("expected distinct CSRs")
	}
}

func TestStageTLSWritesDotNewFiles(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}

	if err := ks.StageTLS([]byte("CHAIN"), []byte("KEY")); err != nil {
		t.Fatalf("StageTLS: %v", err)
	}

	chainPath := filepath.Join(dir, "tls.crt.new")
	keyPath := filepath.Join(dir, "tls.key.new")
	for _, p := range []string{chainPath, keyPath} {
		fi, err := os.Stat(p)
		if err != nil {
			t.Fatalf("stat %s: %v", p, err)
		}
		if fi.Mode().Perm() != 0o600 {
			t.Errorf("%s mode = %v, want 0600", p, fi.Mode().Perm())
		}
	}
}

func TestRollbackStagedTLSRemovesDotNew(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}
	if err := ks.StageTLS([]byte("CHAIN"), []byte("KEY")); err != nil {
		t.Fatalf("StageTLS: %v", err)
	}
	if err := ks.RollbackStagedTLS(); err != nil {
		t.Fatalf("RollbackStagedTLS: %v", err)
	}
	for _, name := range []string{"tls.crt.new", "tls.key.new"} {
		if _, err := os.Stat(filepath.Join(dir, name)); !os.IsNotExist(err) {
			t.Errorf("expected %s removed", name)
		}
	}
}

func TestVerifyStagedTLSAcceptsValid(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}
	rootPEM, intPEM, leafPEM, leafKeyPEM := mkTestChain(t, "h-1")

	// Pin root via StoreEnrollmentBundle (existing API)
	if err := ks.StoreEnrollmentBundle(leafPEM, intPEM, rootPEM); err != nil {
		t.Fatalf("StoreEnrollmentBundle: %v", err)
	}
	chain := append(append([]byte{}, leafPEM...), intPEM...)
	if err := ks.StageTLS(chain, leafKeyPEM); err != nil {
		t.Fatalf("StageTLS: %v", err)
	}
	if err := ks.VerifyStagedTLS(); err != nil {
		t.Fatalf("VerifyStagedTLS: %v", err)
	}
}

func TestVerifyStagedTLSRejectsKeyMismatch(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}
	rootPEM, intPEM, leafPEM, _ := mkTestChain(t, "h-1")
	_, _, _, otherKey := mkTestChain(t, "h-2")
	if err := ks.StoreEnrollmentBundle(leafPEM, intPEM, rootPEM); err != nil {
		t.Fatalf("StoreEnrollmentBundle: %v", err)
	}
	chain := append(append([]byte{}, leafPEM...), intPEM...)
	if err := ks.StageTLS(chain, otherKey); err != nil {
		t.Fatalf("StageTLS: %v", err)
	}
	if err := ks.VerifyStagedTLS(); err == nil {
		t.Fatal("expected error: key mismatch")
	}
}

func TestVerifyStagedTLSRejectsBadChain(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}
	rootPEM, _, _, _ := mkTestChain(t, "h-1")
	otherRoot, otherInt, otherLeaf, otherKey := mkTestChain(t, "h-2")
	_ = otherRoot
	if err := ks.StoreEnrollmentBundle(otherLeaf, otherInt, rootPEM); err != nil {
		// pin against `rootPEM` (different root) so chain won't validate
		t.Fatalf("StoreEnrollmentBundle: %v", err)
	}
	chain := append(append([]byte{}, otherLeaf...), otherInt...)
	if err := ks.StageTLS(chain, otherKey); err != nil {
		t.Fatalf("StageTLS: %v", err)
	}
	if err := ks.VerifyStagedTLS(); err == nil {
		t.Fatal("expected error: chain doesn't validate")
	}
}

func TestCommitTLSAtomicSwap(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}
	// Seed existing tls.crt + tls.key
	if err := os.WriteFile(filepath.Join(dir, "tls.crt"), []byte("OLDCHAIN"), 0o600); err != nil {
		t.Fatalf("seed crt: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "tls.key"), []byte("OLDKEY"), 0o600); err != nil {
		t.Fatalf("seed key: %v", err)
	}
	if err := ks.StageTLS([]byte("NEWCHAIN"), []byte("NEWKEY")); err != nil {
		t.Fatalf("StageTLS: %v", err)
	}
	if err := ks.CommitTLS(); err != nil {
		t.Fatalf("CommitTLS: %v", err)
	}

	got, _ := os.ReadFile(filepath.Join(dir, "tls.crt"))
	if string(got) != "NEWCHAIN" {
		t.Errorf("crt = %q, want NEWCHAIN", got)
	}
	got, _ = os.ReadFile(filepath.Join(dir, "tls.key"))
	if string(got) != "NEWKEY" {
		t.Errorf("key = %q, want NEWKEY", got)
	}
	prev, err := os.ReadFile(filepath.Join(dir, "tls.crt.prev"))
	if err != nil {
		t.Fatalf("expected tls.crt.prev: %v", err)
	}
	if string(prev) != "OLDCHAIN" {
		t.Errorf("prev = %q, want OLDCHAIN", prev)
	}
}

func TestCommitTLSFailsWithoutStaged(t *testing.T) {
	dir := t.TempDir()
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		t.Fatalf("OpenFile: %v", err)
	}
	if err := ks.CommitTLS(); err == nil {
		t.Fatal("expected error: no staged files")
	}
}

// mkTestChain creates a self-signed root + intermediate + leaf for cn.
// Returns PEM of root, intermediate, leaf, and leaf private key (PKCS8 PEM).
func mkTestChain(t *testing.T, cn string) (rootPEM, intPEM, leafPEM, leafKeyPEM []byte) {
	t.Helper()

	// Root CA
	rootKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("root key: %v", err)
	}
	rootTmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "test-root"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageCertSign,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	rootDER, err := x509.CreateCertificate(rand.Reader, rootTmpl, rootTmpl, &rootKey.PublicKey, rootKey)
	if err != nil {
		t.Fatalf("root cert: %v", err)
	}
	rootCert, _ := x509.ParseCertificate(rootDER)
	rootPEM = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: rootDER})

	// Intermediate
	intKey, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	intTmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(2),
		Subject:               pkix.Name{CommonName: "test-int"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageCertSign,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	intDER, err := x509.CreateCertificate(rand.Reader, intTmpl, rootCert, &intKey.PublicKey, rootKey)
	if err != nil {
		t.Fatalf("int cert: %v", err)
	}
	intCert, _ := x509.ParseCertificate(intDER)
	intPEM = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: intDER})

	// Leaf
	leafKey, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	leafTmpl := &x509.Certificate{
		SerialNumber: big.NewInt(3),
		Subject:      pkix.Name{CommonName: cn},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(24 * time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth},
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, leafTmpl, intCert, &leafKey.PublicKey, intKey)
	if err != nil {
		t.Fatalf("leaf cert: %v", err)
	}
	leafPEM = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: leafDER})

	leafKeyDER, _ := x509.MarshalPKCS8PrivateKey(leafKey)
	leafKeyPEM = pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: leafKeyDER})
	return
}
