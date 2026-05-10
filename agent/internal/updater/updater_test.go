package updater

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/hlhelper/hl-agent/internal/logging"
)

func TestApply_HappyPath(t *testing.T) {
	dir := t.TempDir()
	installPath := filepath.Join(dir, "hl-agent")
	if err := os.WriteFile(installPath, []byte("OLD"), 0o755); err != nil {
		t.Fatal(err)
	}
	stateDir := filepath.Join(dir, "state")
	binary := []byte("NEW_BINARY_BYTES_FAKE")
	sum := sha256.Sum256(binary)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(binary)
	}))
	defer srv.Close()
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	body, _ := json.Marshal(Manifest{
		Version: "0.4.2", Channel: "stable", OS: "linux", Arch: "amd64",
		SHA256: hex.EncodeToString(sum[:]), Size: int64(len(binary)),
	})
	sig := ed25519.Sign(priv, body)

	called := false
	u := &Updater{
		StateDir:    stateDir,
		InstallPath: installPath,
		PinnedPub:   pub,
		HTTPClient:  http.DefaultClient,
		Relaunch:    func(string, []string, []string) error { called = true; return nil },
	}
	cmd := Cmd{
		ManifestJSON: body, ManifestSig: sig,
		BinaryURL: srv.URL, ExpectedSHA256: hex.EncodeToString(sum[:]),
		ExpectedSize: int64(len(binary)),
	}
	if err := u.Apply(context.Background(), cmd); err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(installPath)
	if string(got) != string(binary) {
		t.Fatalf("binary not swapped, got %q", got)
	}
	if !called {
		t.Fatal("relaunch not invoked")
	}
	tgt, _, ok := ReadPending(stateDir)
	if !ok || tgt != "0.4.2" {
		t.Fatalf("pending not set: %s %v", tgt, ok)
	}
}

func TestApply_BadSig(t *testing.T) {
	dir := t.TempDir()
	installPath := filepath.Join(dir, "hl-agent")
	os.WriteFile(installPath, []byte("OLD"), 0o755)
	pub, _, _ := ed25519.GenerateKey(rand.Reader)
	u := &Updater{StateDir: filepath.Join(dir, "s"), InstallPath: installPath, PinnedPub: pub}
	body, _ := json.Marshal(Manifest{Version: "0.4.2"})
	bad := make([]byte, ed25519.SignatureSize)
	err := u.Apply(context.Background(), Cmd{ManifestJSON: body, ManifestSig: bad})
	if err == nil {
		t.Fatal("expected sig failure")
	}
	got, _ := os.ReadFile(installPath)
	if string(got) != "OLD" {
		t.Fatal("binary should not be swapped on bad sig")
	}
}

func TestApply_ShaMismatch(t *testing.T) {
	dir := t.TempDir()
	installPath := filepath.Join(dir, "hl-agent")
	os.WriteFile(installPath, []byte("OLD"), 0o755)
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("WRONG"))
	}))
	defer srv.Close()
	body, _ := json.Marshal(Manifest{Version: "0.4.2", SHA256: "deadbeef", Size: 5})
	sig := ed25519.Sign(priv, body)
	u := &Updater{
		StateDir: filepath.Join(dir, "s"), InstallPath: installPath,
		PinnedPub: pub, HTTPClient: http.DefaultClient,
	}
	err := u.Apply(context.Background(), Cmd{
		ManifestJSON: body, ManifestSig: sig,
		BinaryURL: srv.URL, ExpectedSHA256: "deadbeef", ExpectedSize: 5,
	})
	if err == nil {
		t.Fatal("expected sha mismatch")
	}
}

func TestApply_EmitsOnSuccess(t *testing.T) {
	dir := t.TempDir()
	installPath := filepath.Join(dir, "hl-agent")
	if err := os.WriteFile(installPath, []byte("OLD"), 0o755); err != nil {
		t.Fatal(err)
	}
	stateDir := filepath.Join(dir, "state")
	binary := []byte("NEW_BINARY_BYTES_FAKE")
	sum := sha256.Sum256(binary)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(binary)
	}))
	defer srv.Close()
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	body, _ := json.Marshal(Manifest{
		Version: "0.4.2", Channel: "stable", OS: "linux", Arch: "amd64",
		SHA256: hex.EncodeToString(sum[:]), Size: int64(len(binary)),
	})
	sig := ed25519.Sign(priv, body)

	fake := &logging.FakeEmitter{}
	u := &Updater{
		StateDir:    stateDir,
		InstallPath: installPath,
		CurrentVer:  "0.4.1",
		PinnedPub:   pub,
		HTTPClient:  http.DefaultClient,
		Relaunch:    func(string, []string, []string) error { return nil },
		Emitter:     fake,
	}
	cmd := Cmd{
		ManifestJSON: body, ManifestSig: sig,
		BinaryURL: srv.URL, ExpectedSHA256: hex.EncodeToString(sum[:]),
		ExpectedSize: int64(len(binary)),
	}
	if err := u.Apply(context.Background(), cmd); err != nil {
		t.Fatal(err)
	}
	if len(fake.Events) != 1 {
		t.Fatalf("want 1 event, got %d", len(fake.Events))
	}
	ev := fake.Events[0]
	if ev.Action != "update.swap.completed" {
		t.Fatalf("want action=update.swap.completed, got %s", ev.Action)
	}
	if ev.Category != "update" {
		t.Fatalf("want category=update, got %s", ev.Category)
	}
}
