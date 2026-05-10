package updater

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"github.com/hlhelper/hl-agent/internal/logging"
)

type Cmd struct {
	ReleaseID      string
	ManifestJSON   []byte
	ManifestSig    []byte
	BinaryURL      string
	DownloadToken  string
	ExpectedSHA256 string
	ExpectedSize   int64
	Force          bool
}

// RelaunchFn replaces the current process. Production: wraps syscall.Exec.
type RelaunchFn func(argv0 string, argv []string, envv []string) error


type Updater struct {
	StateDir    string
	InstallPath string
	CurrentVer  string
	PinnedPub   ed25519.PublicKey
	HTTPClient  *http.Client
	Relaunch    RelaunchFn
	Emitter     logging.EventEmitter // optional; if set, activity events are recorded
}

var (
	ErrSHAMismatch  = errors.New("binary sha256 mismatch")
	ErrSizeMismatch = errors.New("binary size mismatch")
)

func (u *Updater) Apply(ctx context.Context, cmd Cmd) error {
	manifest, err := VerifyManifest(cmd.ManifestJSON, cmd.ManifestSig, u.PinnedPub)
	if err != nil {
		return fmt.Errorf("verify manifest: %w", err)
	}
	if !cmd.Force && manifest.Version == u.CurrentVer {
		return fmt.Errorf("already on %s", manifest.Version)
	}

	newDir := filepath.Join(u.StateDir, manifest.Version)
	if err := os.MkdirAll(newDir, 0o755); err != nil {
		return err
	}
	newPath := filepath.Join(newDir, "hl-agent.new")

	if err := u.download(ctx, cmd.BinaryURL, cmd.DownloadToken, newPath); err != nil {
		if u.Emitter != nil {
			u.Emitter.EmitErr(4, "update", "update.swap.failed", "download failed", "DOWNLOAD_FAILED", err.Error(), map[string]any{
				"from": u.CurrentVer,
				"to":   manifest.Version,
			})
		}
		return fmt.Errorf("download: %w", err)
	}
	if err := verifyFile(newPath, cmd.ExpectedSHA256, cmd.ExpectedSize); err != nil {
		_ = os.Remove(newPath)
		if u.Emitter != nil {
			u.Emitter.EmitErr(4, "update", "update.swap.failed", "verify failed", "VERIFY_FAILED", err.Error(), map[string]any{
				"from": u.CurrentVer,
				"to":   manifest.Version,
			})
		}
		return err
	}
	if err := os.Chmod(newPath, 0o755); err != nil {
		return err
	}

	prevDir := filepath.Join(u.StateDir, "_prev")
	if err := os.MkdirAll(prevDir, 0o755); err != nil {
		return err
	}
	prevPath := filepath.Join(prevDir, "hl-agent.prev")
	if _, err := os.Stat(u.InstallPath); err == nil {
		if err := copyFile(u.InstallPath, prevPath); err != nil {
			return fmt.Errorf("backup current: %w", err)
		}
	}

	if err := MarkPending(u.StateDir, manifest.Version, prevPath); err != nil {
		return err
	}

	if err := os.Rename(newPath, u.InstallPath); err != nil {
		return fmt.Errorf("swap: %w", err)
	}

	// Emit success event on swap
	if u.Emitter != nil {
		u.Emitter.Emit(0, "update", "update.swap.completed", "agent updated", map[string]any{
			"from": u.CurrentVer,
			"to":   manifest.Version,
		})
	}

	if u.Relaunch == nil {
		return errors.New("no Relaunch func configured")
	}
	return u.Relaunch(u.InstallPath, []string{u.InstallPath}, os.Environ())
}

func (u *Updater) download(ctx context.Context, url, token, dst string) error {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}
	if token != "" {
		q := req.URL.Query()
		q.Set("token", token)
		req.URL.RawQuery = q.Encode()
	}
	resp, err := u.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("http %d", resp.StatusCode)
	}
	f, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(f, resp.Body)
	return err
}

func verifyFile(path, expectedHex string, expectedSize int64) error {
	st, err := os.Stat(path)
	if err != nil {
		return err
	}
	if expectedSize > 0 && st.Size() != expectedSize {
		return ErrSizeMismatch
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return err
	}
	if hex.EncodeToString(h.Sum(nil)) != expectedHex {
		return ErrSHAMismatch
	}
	return nil
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	if _, err := io.Copy(out, in); err != nil {
		return err
	}
	return os.Chmod(dst, 0o755)
}
