package decom_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/hlhelper/hl-agent/internal/decom"
)

func TestRunRemovesSensitiveFiles(t *testing.T) {
	tmpdir := t.TempDir()

	// Create all target files
	files := []string{
		"signing.key",
		"tls.key",
		"manifest.json",
		"outbox.db",
		"tpm-handle.bin",
	}
	for _, f := range files {
		fpath := filepath.Join(tmpdir, f)
		if err := os.WriteFile(fpath, []byte("sensitive data"), 0600); err != nil {
			t.Fatal(err)
		}
	}

	// Run decommission
	err := decom.Run(decom.Options{
		Dir:       tmpdir,
		Force:     true,
		Overwrite: 1,
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	// Verify all files are deleted
	for _, f := range files {
		fpath := filepath.Join(tmpdir, f)
		if _, err := os.Stat(fpath); !os.IsNotExist(err) {
			t.Errorf("file %s should have been deleted", f)
		}
	}
}

func TestRunOverwritesBeforeUnlink(t *testing.T) {
	tmpdir := t.TempDir()

	signingKeyPath := filepath.Join(tmpdir, "signing.key")
	if err := os.WriteFile(signingKeyPath, []byte("secret"), 0600); err != nil {
		t.Fatal(err)
	}

	err := decom.Run(decom.Options{
		Dir:       tmpdir,
		Force:     true,
		Overwrite: 2,
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	// Verify file is deleted
	if _, err := os.Stat(signingKeyPath); !os.IsNotExist(err) {
		t.Error("signing.key should have been deleted")
	}
}

func TestRunIgnoresMissingFiles(t *testing.T) {
	tmpdir := t.TempDir()

	// Run on empty directory
	err := decom.Run(decom.Options{
		Dir:       tmpdir,
		Force:     true,
		Overwrite: 1,
	})
	if err != nil {
		t.Fatalf("Run should not error on missing files: %v", err)
	}
}

func TestRunHandlesSymlinkSafely(t *testing.T) {
	tmpdir := t.TempDir()

	// Create external sensitive file
	externalFile := filepath.Join(tmpdir, "external-secret.txt")
	if err := os.WriteFile(externalFile, []byte("external secret"), 0600); err != nil {
		t.Fatal(err)
	}

	// Create symlink to it
	symlinkPath := filepath.Join(tmpdir, "signing.key")
	if err := os.Symlink(externalFile, symlinkPath); err != nil {
		t.Fatal(err)
	}

	// Run decommission
	err := decom.Run(decom.Options{
		Dir:       tmpdir,
		Force:     true,
		Overwrite: 1,
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	// Verify symlink is removed
	if _, err := os.Lstat(symlinkPath); !os.IsNotExist(err) {
		t.Error("signing.key symlink should have been deleted")
	}

	// Verify external file is untouched
	data, err := os.ReadFile(externalFile)
	if err != nil {
		t.Fatalf("external file should still exist: %v", err)
	}
	if string(data) != "external secret" {
		t.Error("external file should not have been modified")
	}
}

func TestRunCleavesDirectoryStructure(t *testing.T) {
	tmpdir := t.TempDir()

	// Create subdirectories and files
	if err := os.MkdirAll(filepath.Join(tmpdir, "subdir"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(tmpdir, "signing.key"), []byte("secret"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(tmpdir, "subdir", "other.txt"), []byte("keep"), 0600); err != nil {
		t.Fatal(err)
	}

	err := decom.Run(decom.Options{
		Dir:       tmpdir,
		Force:     true,
		Overwrite: 1,
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	// Verify signing.key is gone
	if _, err := os.Stat(filepath.Join(tmpdir, "signing.key")); !os.IsNotExist(err) {
		t.Error("signing.key should have been deleted")
	}

	// Verify directory and other files remain
	if _, err := os.Stat(tmpdir); os.IsNotExist(err) {
		t.Error("directory should still exist")
	}
	if _, err := os.Stat(filepath.Join(tmpdir, "subdir")); os.IsNotExist(err) {
		t.Error("subdirectory should still exist")
	}
	data, err := os.ReadFile(filepath.Join(tmpdir, "subdir", "other.txt"))
	if err != nil || string(data) != "keep" {
		t.Error("other.txt should be untouched")
	}
}
