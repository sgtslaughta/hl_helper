package updater

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"testing"
)

func TestVerifyManifest_Valid(t *testing.T) {
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	body, _ := json.Marshal(map[string]any{
		"version": "0.4.2", "channel": "stable",
		"os": "linux", "arch": "amd64",
		"sha256": "deadbeef", "size": 100,
	})
	sig := ed25519.Sign(priv, body)
	m, err := VerifyManifest(body, sig, pub)
	if err != nil {
		t.Fatal(err)
	}
	if m.Version != "0.4.2" {
		t.Fatalf("got %s", m.Version)
	}
}

func TestVerifyManifest_TamperedSig(t *testing.T) {
	pub, _, _ := ed25519.GenerateKey(rand.Reader)
	body := []byte(`{"version":"0.4.2"}`)
	bad := make([]byte, ed25519.SignatureSize)
	if _, err := VerifyManifest(body, bad, pub); err == nil {
		t.Fatal("expected verify failure")
	}
}

func TestVerifyManifest_TamperedBody(t *testing.T) {
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	body := []byte(`{"version":"0.4.2"}`)
	sig := ed25519.Sign(priv, body)
	if _, err := VerifyManifest([]byte(`{"version":"9.9.9"}`), sig, pub); err == nil {
		t.Fatal("expected verify failure")
	}
}
