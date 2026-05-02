// Package decom performs agent decommissioning: securely wipes keystore + outbox.
package decom

import (
	"crypto/rand"
	"fmt"
	"os"
	"path/filepath"
)

type Options struct {
	Dir       string // keystore + outbox dir
	Force     bool   // skip confirmation
	Overwrite int    // pass count for secure wipe (default 1)
}

// Run zeroes + unlinks: signing.key, tls.key, manifest.json, outbox.db, tpm-handle.bin.
// Leaves dir itself intact (parent may persist).
func Run(opts Options) error {
	targetFiles := []string{
		"signing.key",
		"tls.key",
		"manifest.json",
		"outbox.db",
		"tpm-handle.bin",
	}

	for _, filename := range targetFiles {
		fpath := filepath.Join(opts.Dir, filename)

		// Use Lstat to detect symlinks without following them
		info, err := os.Lstat(fpath)
		if err != nil {
			if os.IsNotExist(err) {
				continue // file doesn't exist, skip
			}
			return fmt.Errorf("stat %s: %w", filename, err)
		}

		// If symlink, just unlink without overwriting
		if info.Mode()&os.ModeSymlink != 0 {
			if err := os.Remove(fpath); err != nil {
				return fmt.Errorf("remove symlink %s: %w", filename, err)
			}
			continue
		}

		// Regular file: overwrite then unlink
		if err := secureWipe(fpath, opts.Overwrite); err != nil {
			return err
		}

		if err := os.Remove(fpath); err != nil {
			return fmt.Errorf("remove %s: %w", filename, err)
		}
	}

	return nil
}

func secureWipe(path string, passes int) error {
	file, err := os.OpenFile(path, os.O_WRONLY, 0)
	if err != nil {
		return fmt.Errorf("open %s for wipe: %w", path, err)
	}
	defer file.Close()

	info, err := file.Stat()
	if err != nil {
		return fmt.Errorf("stat file: %w", err)
	}
	size := info.Size()

	for pass := 0; pass < passes; pass++ {
		if _, err := file.Seek(0, 0); err != nil {
			return fmt.Errorf("seek in %s: %w", path, err)
		}

		buf := make([]byte, 8192)
		remaining := size
		for remaining > 0 {
			toWrite := int64(len(buf))
			if toWrite > remaining {
				toWrite = remaining
			}

			if _, err := rand.Read(buf[:toWrite]); err != nil {
				return fmt.Errorf("rand: %w", err)
			}

			if _, err := file.Write(buf[:toWrite]); err != nil {
				return fmt.Errorf("write to %s: %w", path, err)
			}

			remaining -= toWrite
		}

		if err := file.Sync(); err != nil {
			return fmt.Errorf("sync %s: %w", path, err)
		}
	}

	return nil
}
