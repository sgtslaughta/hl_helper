package verify

import (
	"crypto/ed25519"
	"fmt"
	"testing"
	"time"

	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

func TestAcceptValidCommand(t *testing.T) {
	// Generate test key pair
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	// Build a valid envelope
	env := &pb.CommandEnvelope{
		CommandId: "cmd-123",
		HostId:    "host-1",
		Sequence:  1,
		Nonce:     []byte("nonce-001"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
	}

	// Sign it
	canonBytes := canonicalBytesFn(env)
	sig := ed25519.Sign(priv, canonBytes)
	env.Signature = sig

	// Create verifier
	v := New(pub, []string{"shell.exec"}, "high")

	// Accept should not error
	err = v.Accept(env, now)
	if err != nil {
		t.Errorf("Accept failed: %v", err)
	}
}

func TestRejectsBadSignature(t *testing.T) {
	pub, _, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	env := &pb.CommandEnvelope{
		CommandID:   "cmd-123",
		HostID:      "host-1",
		Sequence:    1,
		Nonce:       []byte("nonce-001"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
		Signature:   []byte("bad-signature-data"),
	}

	v := New(pub, []string{"shell.exec"}, "high")
	err = v.Accept(env, now)
	if err != ErrBadSignature {
		t.Errorf("Expected ErrBadSignature, got %v", err)
	}
}

func TestRejectsDisallowedAction(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	// ShellExec is NOT in allowed list
	env := &pb.CommandEnvelope{
		CommandID:   "cmd-123",
		HostID:      "host-1",
		Sequence:    1,
		Nonce:       []byte("nonce-001"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes := canonicalBytesFn(env)
	sig := ed25519.Sign(priv, canonBytes)
	env.Signature = sig

	// Only allow pkg.update
	v := New(pub, []string{"pkg.update"}, "high")
	err = v.Accept(env, now)
	if err != ErrActionNotAllowed {
		t.Errorf("Expected ErrActionNotAllowed, got %v", err)
	}
}

func TestRejectsHighRiskAboveLimit(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	// Risk is CRITICAL, max allowed is MEDIUM
	env := &pb.CommandEnvelope{
		CommandID:   "cmd-123",
		HostID:      "host-1",
		Sequence:    1,
		Nonce:       []byte("nonce-001"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_HIGH, // Will use high, but test with critical
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	// Manually set to 3 (critical) since our pb shim doesn't have it
	env.Risk = 3

	canonBytes := canonicalBytesFn(env)
	sig := ed25519.Sign(priv, canonBytes)
	env.Signature = sig

	// Max risk is medium (1)
	v := New(pub, []string{"shell.exec"}, "medium")
	err = v.Accept(env, now)
	if err != ErrRiskTooHigh {
		t.Errorf("Expected ErrRiskTooHigh, got %v", err)
	}
}

func TestRejectsExpired(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	past := now.Add(-1 * time.Minute) // Expired 1 minute ago

	env := &pb.CommandEnvelope{
		CommandID:   "cmd-123",
		HostID:      "host-1",
		Sequence:    1,
		Nonce:       []byte("nonce-001"),
		IssuedAt:    &past,
		ExpiresAt:   &past,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes := canonicalBytesFn(env)
	sig := ed25519.Sign(priv, canonBytes)
	env.Signature = sig

	v := New(pub, []string{"shell.exec"}, "high")
	err = v.Accept(env, now)
	if err != ErrExpired {
		t.Errorf("Expected ErrExpired, got %v", err)
	}
}

func TestRejectsClockSkew(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	future := now.Add(10 * time.Minute) // Issued 10 minutes in the future
	exp := future.Add(5 * time.Minute)

	env := &pb.CommandEnvelope{
		CommandID:   "cmd-123",
		HostID:      "host-1",
		Sequence:    1,
		Nonce:       []byte("nonce-001"),
		IssuedAt:    &future,
		ExpiresAt:   &exp,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes := canonicalBytesFn(env)
	sig := ed25519.Sign(priv, canonBytes)
	env.Signature = sig

	// Default skew is 60 seconds, so 10 minutes should fail
	v := New(pub, []string{"shell.exec"}, "high")
	err = v.Accept(env, now)
	if err != ErrExpired {
		t.Errorf("Expected ErrExpired (clock skew), got %v", err)
	}
}

func TestRejectsReplayedSequence(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	// First envelope with sequence 5
	env1 := &pb.CommandEnvelope{
		CommandID:   "cmd-1",
		HostID:      "host-1",
		Sequence:    5,
		Nonce:       []byte("nonce-001"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes1 := canonicalBytesFn(env1)
	sig1 := ed25519.Sign(priv, canonBytes1)
	env1.Signature = sig1

	v := New(pub, []string{"shell.exec"}, "high")

	// Accept first command
	if err := v.Accept(env1, now); err != nil {
		t.Fatalf("Accept env1 failed: %v", err)
	}

	// Second envelope with same or lower sequence
	env2 := &pb.CommandEnvelope{
		CommandID:   "cmd-2",
		HostID:      "host-1",
		Sequence:    5, // Same sequence
		Nonce:       []byte("nonce-002"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes2 := canonicalBytesFn(env2)
	sig2 := ed25519.Sign(priv, canonBytes2)
	env2.Signature = sig2

	err = v.Accept(env2, now)
	if err != ErrReplay {
		t.Errorf("Expected ErrReplay, got %v", err)
	}
}

func TestRejectsReplayedNonce(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	// First envelope
	env1 := &pb.CommandEnvelope{
		CommandID:   "cmd-1",
		HostID:      "host-1",
		Sequence:    1,
		Nonce:       []byte("nonce-001"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes1 := canonicalBytesFn(env1)
	sig1 := ed25519.Sign(priv, canonBytes1)
	env1.Signature = sig1

	v := New(pub, []string{"shell.exec"}, "high")

	if err := v.Accept(env1, now); err != nil {
		t.Fatalf("Accept env1 failed: %v", err)
	}

	// Second envelope with same nonce, different sequence
	env2 := &pb.CommandEnvelope{
		CommandID:   "cmd-2",
		HostID:      "host-1",
		Sequence:    2,
		Nonce:       []byte("nonce-001"), // Same nonce!
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes2 := canonicalBytesFn(env2)
	sig2 := ed25519.Sign(priv, canonBytes2)
	env2.Signature = sig2

	err = v.Accept(env2, now)
	if err != ErrReplay {
		t.Errorf("Expected ErrReplay (nonce), got %v", err)
	}
}

func TestNonceLRUEviction(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	// Create verifier with nonce cap of 3
	v := New(pub, []string{"shell.exec"}, "high",
		WithNonceCap(3))

	// Add 5 envelopes with different nonces
	for i := 1; i <= 5; i++ {
		numStr := fmt.Sprintf("%d", i)
		env := &pb.CommandEnvelope{
			CommandID:   "cmd-" + numStr,
			HostID:      "host-1",
			Sequence:    uint64(i),
			Nonce:       []byte("nonce-" + numStr),
			IssuedAt:    &now,
			ExpiresAt:   &fut,
			IssuedBy:    "server",
			Risk:        pb.RISK_LOW,
			Capability:  &pb.CapabilityToken{},
			ShellExec:   &pb.ShellExec{Command: "ls"},
		}

		canonBytes := canonicalBytesFn(env)
		sig := ed25519.Sign(priv, canonBytes)
		env.Signature = sig

		if err := v.Accept(env, now); err != nil {
			t.Fatalf("Accept env %d failed: %v", i, err)
		}
	}

	// Now nonces 1 and 2 should be evicted; 3, 4, 5 remain
	// Try to replay nonce 1 (oldest, should be allowed as it was evicted)
	env1Replay := &pb.CommandEnvelope{
		CommandID:   "cmd-replay-1",
		HostID:      "host-1",
		Sequence:    6,
		Nonce:       []byte("nonce-1"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes := canonicalBytesFn(env1Replay)
	sig := ed25519.Sign(priv, canonBytes)
	env1Replay.Signature = sig

	// Should succeed because nonce-1 was evicted
	if err := v.Accept(env1Replay, now); err != nil {
		t.Errorf("Replay of evicted nonce-1 should succeed, got %v", err)
	}

	// Try to replay nonce 3 (should still be in map)
	env3Replay := &pb.CommandEnvelope{
		CommandID:   "cmd-replay-3",
		HostID:      "host-1",
		Sequence:    7,
		Nonce:       []byte("nonce-3"),
		IssuedAt:    &now,
		ExpiresAt:   &fut,
		IssuedBy:    "server",
		Risk:        pb.RISK_LOW,
		Capability:  &pb.CapabilityToken{},
		ShellExec:   &pb.ShellExec{Command: "ls"},
	}

	canonBytes = canonicalBytesFn(env3Replay)
	sig = ed25519.Sign(priv, canonBytes)
	env3Replay.Signature = sig

	err = v.Accept(env3Replay, now)
	if err != ErrReplay {
		t.Errorf("Replay of nonce-3 should fail, got %v", err)
	}
}

// canonicalBytesFn delegates to the package-internal canonicalMsg so tests
// match production signing semantics exactly.
func canonicalBytesFn(env *pb.CommandEnvelope) []byte {
	cp := *env
	cp.Signature = nil
	return canonicalMsg(&cp)
}

func encodeUint64(v uint64) []byte {
	b := make([]byte, 8)
	for i := 0; i < 8; i++ {
		b[i] = byte(v >> (uint(i) * 8))
	}
	return b
}

func encodeInt64(v int64) []byte {
	b := make([]byte, 8)
	for i := 0; i < 8; i++ {
		b[i] = byte(v >> (uint(i) * 8))
	}
	return b
}

func encodeInt32(v int32) []byte {
	b := make([]byte, 4)
	for i := 0; i < 4; i++ {
		b[i] = byte(v >> (uint(i) * 8))
	}
	return b
}
