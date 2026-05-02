package keystore_test

import (
	"crypto/ed25519"
	"os"
	"path/filepath"
	"testing"

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

	// Check key
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
