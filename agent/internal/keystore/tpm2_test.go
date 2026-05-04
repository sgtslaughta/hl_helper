package keystore_test

import (
	"crypto/ed25519"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/keystore"
)

// setupSwtpm starts a software TPM simulator in socket mode.
// Returns the socket path and a cleanup function.
// If swtpm is not available, returns ("", nil).
func setupSwtpm(t *testing.T) (string, func()) {
	if _, err := exec.LookPath("swtpm"); err != nil {
		t.Skip("swtpm not available; install with: apt install swtpm")
	}

	tmpdir := t.TempDir()
	sockPath := filepath.Join(tmpdir, "tpm.sock")

	cmd := exec.Command("swtpm", "socket", "--tpmstate", "dir="+tmpdir, "--ctrl", "type=unixio,path="+sockPath)
	cmd.Stdout = nil
	cmd.Stderr = nil

	if err := cmd.Start(); err != nil {
		t.Fatalf("failed to start swtpm: %v", err)
	}

	// Wait for socket to be available
	for i := 0; i < 50; i++ {
		if _, err := os.Stat(sockPath); err == nil {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}

	cleanup := func() {
		cmd.Process.Kill()
		cmd.Wait()
	}

	return sockPath, cleanup
}

func TestOpenTPMRequiresExistingDir(t *testing.T) {
	sockPath, cleanup := setupSwtpm(t)
	if cleanup != nil {
		defer cleanup()
	}

	_, err := keystore.OpenTPM(sockPath, "/nonexistent/path")
	if err == nil {
		t.Fatal("expected error for non-existent dir")
	}
}

func TestGenerateSigningCreatesTPMHandle(t *testing.T) {
	sockPath, cleanup := setupSwtpm(t)
	if cleanup != nil {
		defer cleanup()
	}

	tmpdir := t.TempDir()
	ks, err := keystore.OpenTPM(sockPath, tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM failed: %v", err)
	}
	defer ks.Close()

	err = ks.GenerateSigning()
	if err != nil {
		t.Fatalf("GenerateSigning failed: %v", err)
	}

	// Check that handle file was written
	handlePath := filepath.Join(tmpdir, "tpm-handle.bin")
	_, err = os.Stat(handlePath)
	if err != nil {
		t.Fatalf("tpm-handle.bin not created: %v", err)
	}

	// Check that pub file was written
	pubPath := filepath.Join(tmpdir, "tpm-pub.pem")
	_, err = os.Stat(pubPath)
	if err != nil {
		t.Fatalf("tpm-pub.pem not created: %v", err)
	}

	// Second call should be idempotent
	err = ks.GenerateSigning()
	if err != nil {
		t.Fatalf("second GenerateSigning failed: %v", err)
	}

	pub1 := ks.SigningPub()
	if pub1 == nil {
		t.Fatal("SigningPub returned nil")
	}
}

func TestSignAndVerifyRoundtripViaTPM(t *testing.T) {
	sockPath, cleanup := setupSwtpm(t)
	if cleanup != nil {
		defer cleanup()
	}

	tmpdir := t.TempDir()
	ks, err := keystore.OpenTPM(sockPath, tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM failed: %v", err)
	}
	defer ks.Close()

	err = ks.GenerateSigning()
	if err != nil {
		t.Fatalf("GenerateSigning failed: %v", err)
	}

	msg := []byte("test message")
	sig, err := ks.Sign(msg)
	if err != nil {
		t.Fatalf("Sign failed: %v", err)
	}

	pubKey := ks.SigningPub()
	if !ed25519.Verify(pubKey, msg, sig) {
		t.Fatal("signature verification failed")
	}
}

func TestTPMPersistenceAcrossOpens(t *testing.T) {
	sockPath, cleanup := setupSwtpm(t)
	if cleanup != nil {
		defer cleanup()
	}

	tmpdir := t.TempDir()

	// First open: create and sign
	ks1, err := keystore.OpenTPM(sockPath, tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM failed: %v", err)
	}

	err = ks1.GenerateSigning()
	if err != nil {
		t.Fatalf("GenerateSigning failed: %v", err)
	}

	msg := []byte("test message")
	sig1, err := ks1.Sign(msg)
	if err != nil {
		t.Fatalf("Sign failed: %v", err)
	}

	pub1 := ks1.SigningPub()
	ks1.Close()

	// Second open: load and verify public key + sign same message
	ks2, err := keystore.OpenTPM(sockPath, tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM failed on reopen: %v", err)
	}
	defer ks2.Close()

	pub2 := ks2.SigningPub()
	if !pub1.Equal(pub2) {
		t.Fatal("public key doesn't match after reopening")
	}

	sig2, err := ks2.Sign(msg)
	if err != nil {
		t.Fatalf("Sign failed on reopen: %v", err)
	}

	if string(sig1) != string(sig2) {
		t.Fatal("signature is not deterministic")
	}
}

func TestTPMSignWithoutGenerateErrors(t *testing.T) {
	sockPath, cleanup := setupSwtpm(t)
	if cleanup != nil {
		defer cleanup()
	}

	tmpdir := t.TempDir()
	ks, err := keystore.OpenTPM(sockPath, tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM failed: %v", err)
	}
	defer ks.Close()

	_, err = ks.Sign([]byte("test"))
	if err == nil {
		t.Fatal("expected error when signing without generating key")
	}
}

func TestGenerateTLSDelegatesToFile(t *testing.T) {
	sockPath, cleanup := setupSwtpm(t)
	if cleanup != nil {
		defer cleanup()
	}

	tmpdir := t.TempDir()
	ks, err := keystore.OpenTPM(sockPath, tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM failed: %v", err)
	}
	defer ks.Close()

	err = ks.GenerateTLS()
	if err != nil {
		t.Fatalf("GenerateTLS failed: %v", err)
	}

	// Check that tls.key was created
	keyPath := filepath.Join(tmpdir, "tls.key")
	info, err := os.Stat(keyPath)
	if err != nil {
		t.Fatalf("tls.key not created: %v", err)
	}
	if mode := info.Mode().Perm(); mode != 0600 {
		t.Fatalf("tls.key mode = %o, want 0600", mode)
	}
}

func TestStoreEnrollmentBundleDelegatesToFile(t *testing.T) {
	sockPath, cleanup := setupSwtpm(t)
	if cleanup != nil {
		defer cleanup()
	}

	tmpdir := t.TempDir()
	ks, err := keystore.OpenTPM(sockPath, tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM failed: %v", err)
	}
	defer ks.Close()

	leafPEM := []byte("LEAF CERT")
	intermediatePEM := []byte("INTERMEDIATE CERT")
	rootPEM := []byte("ROOT CERT")

	err = ks.StoreEnrollmentBundle(leafPEM, intermediatePEM, rootPEM)
	if err != nil {
		t.Fatalf("StoreEnrollmentBundle failed: %v", err)
	}

	// Verify files exist
	for _, fn := range []string{"tls.crt", "intermediate.crt", "root.crt"} {
		_, err := os.Stat(filepath.Join(tmpdir, fn))
		if err != nil {
			t.Fatalf("%s not created: %v", fn, err)
		}
	}
}

// ----- failure-mode tests (do not require swtpm) -----

func TestOpenTPMFallsBackOnUnavailableDevice(t *testing.T) {
	// Nonexistent device path -- TPM transport open fails, but constructor
	// must succeed (rw=nil) so caller can detect by checking subsequent ops.
	tmpdir := t.TempDir()
	ks, err := keystore.OpenTPM("/dev/nonexistent-tpm-xyz", tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM should fall back gracefully when device missing: %v", err)
	}
	defer ks.Close()
	if ks == nil {
		t.Fatal("OpenTPM returned nil keystore")
	}
}

func TestOpenTPMRejectsNonexistentDir(t *testing.T) {
	_, err := keystore.OpenTPM("/dev/null", "/nonexistent/path/hl-tpm-test")
	if err == nil {
		t.Fatal("OpenTPM should fail for nonexistent dir")
	}
}

func TestOpenTPMRejectsFilePathAsDir(t *testing.T) {
	tmpdir := t.TempDir()
	filePath := filepath.Join(tmpdir, "not-a-dir")
	if err := os.WriteFile(filePath, []byte("x"), 0600); err != nil {
		t.Fatalf("setup: %v", err)
	}
	_, err := keystore.OpenTPM("/dev/null", filePath)
	if err == nil {
		t.Fatal("OpenTPM should reject file path as keystore dir")
	}
}

func TestOpenTPMHandleFileCorruptDetected(t *testing.T) {
	// Pre-seed the dir with a corrupt handle file (wrong byte count).
	// After OpenTPM the handle should remain unset (loadTPMHandle returns
	// internal error but does not crash); further Sign/SigningPub are nil/0.
	tmpdir := t.TempDir()
	corrupt := []byte{0x01, 0x02, 0x03} // 3 bytes, expected 4
	if err := os.WriteFile(filepath.Join(tmpdir, keystore.TPMHandleFile), corrupt, 0600); err != nil {
		t.Fatalf("setup: %v", err)
	}
	ks, err := keystore.OpenTPM("/dev/null", tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM should not fail outright on corrupt handle: %v", err)
	}
	defer ks.Close()
	if ks.SigningPub() != nil {
		t.Errorf("expected SigningPub() == nil after corrupt handle load, got %x", ks.SigningPub())
	}
}

func TestOpenTPMBadPubKeyFile(t *testing.T) {
	// Valid handle (4 bytes) + corrupt pub PEM file -> graceful fallback
	tmpdir := t.TempDir()
	handleBytes := []byte{0x81, 0x00, 0x00, 0x01}
	if err := os.WriteFile(filepath.Join(tmpdir, keystore.TPMHandleFile), handleBytes, 0600); err != nil {
		t.Fatalf("setup: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmpdir, keystore.TPMPubFile), []byte("NOT A PEM"), 0600); err != nil {
		t.Fatalf("setup: %v", err)
	}
	ks, err := keystore.OpenTPM("/dev/null", tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM should not fail on bad PEM (graceful load): %v", err)
	}
	defer ks.Close()
	// pub stays nil -- caller can detect and decide to regenerate or fail closed
	if ks.SigningPub() != nil {
		t.Errorf("expected nil SigningPub after bad pub PEM, got non-nil")
	}
}

func TestSignWithoutGenerateReturnsError(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenTPM("/dev/nonexistent", tmpdir)
	if err != nil {
		t.Fatalf("OpenTPM: %v", err)
	}
	defer ks.Close()

	if _, err := ks.Sign([]byte("payload")); err == nil {
		t.Fatal("Sign should fail when no key has been generated/loaded")
	}
}

// ensure ed25519 import isn't dropped if other tests in this file ever stop using it
var _ = ed25519.PublicKey(nil)
