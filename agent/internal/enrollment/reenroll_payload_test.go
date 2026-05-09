package enrollment

import (
	"crypto/ed25519"
	"testing"
)

func TestCanonicalReenrollPayloadDeterministic(t *testing.T) {
	a := CanonicalReenrollPayload("h-1", []byte{0xaa, 0xbb}, 1700000000)
	b := CanonicalReenrollPayload("h-1", []byte{0xaa, 0xbb}, 1700000000)
	if !bytesEqual(a, b) {
		t.Fatalf("payloads differ: %x vs %x", a, b)
	}
	if len(a) != 32 {
		t.Errorf("expected sha256 digest (32 bytes), got %d", len(a))
	}
}

func TestSignAndVerifyReenrollPayload(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	msg := CanonicalReenrollPayload("h-1", []byte("nonce"), 1700000000)
	sig := ed25519.Sign(priv, msg)
	if !ed25519.Verify(pub, msg, sig) {
		t.Fatal("verify failed")
	}
}

func bytesEqual(a, b []byte) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
