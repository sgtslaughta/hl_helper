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
		Signature: []byte("bad-signature-data"),
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

	// Risk is HIGH, max allowed is MEDIUM
	env := &pb.CommandEnvelope{
		CommandId: "cmd-123",
		HostId:    "host-1",
		Sequence:  1,
		Nonce:     []byte("nonce-001"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_HIGH,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
	}

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
		CommandId: "cmd-123",
		HostId:    "host-1",
		Sequence:  1,
		Nonce:     []byte("nonce-001"),
		IssuedAt:  timestamppb.New(past),
		ExpiresAt: timestamppb.New(past),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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
		CommandId: "cmd-123",
		HostId:    "host-1",
		Sequence:  1,
		Nonce:     []byte("nonce-001"),
		IssuedAt:  timestamppb.New(future),
		ExpiresAt: timestamppb.New(exp),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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
		CommandId: "cmd-1",
		HostId:    "host-1",
		Sequence:  5,
		Nonce:     []byte("nonce-001"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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
		CommandId: "cmd-2",
		HostId:    "host-1",
		Sequence:  5, // Same sequence
		Nonce:     []byte("nonce-002"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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
		CommandId: "cmd-1",
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

	canonBytes1 := canonicalBytesFn(env1)
	sig1 := ed25519.Sign(priv, canonBytes1)
	env1.Signature = sig1

	v := New(pub, []string{"shell.exec"}, "high")

	if err := v.Accept(env1, now); err != nil {
		t.Fatalf("Accept env1 failed: %v", err)
	}

	// Second envelope with same nonce, different sequence
	env2 := &pb.CommandEnvelope{
		CommandId: "cmd-2",
		HostId:    "host-1",
		Sequence:  2,
		Nonce:     []byte("nonce-001"), // Same nonce!
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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

	// Create verifier with nonce cap of 4. After inserting 5 nonces, the FIFO
	// eviction drops nonce-1 (oldest) leaving {2,3,4,5}. Replaying nonce-1
	// re-inserts it, evicting nonce-2 → {3,4,5,1}. nonce-3 remains, so its
	// replay is rejected.
	v := New(pub, []string{"shell.exec"}, "high",
		WithNonceCap(4))

	// Add 5 envelopes with different nonces
	for i := 1; i <= 5; i++ {
		numStr := fmt.Sprintf("%d", i)
		env := &pb.CommandEnvelope{
			CommandId: "cmd-" + numStr,
			HostId:    "host-1",
			Sequence:  uint64(i),
			Nonce:     []byte("nonce-" + numStr),
			IssuedAt:  timestamppb.New(now),
			ExpiresAt: timestamppb.New(fut),
			IssuedBy:  "server",
			Risk:      pb.RiskLevel_RISK_LOW,
			Capability: &pb.CapabilityToken{},
			Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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
		CommandId: "cmd-replay-1",
		HostId:    "host-1",
		Sequence:  6,
		Nonce:     []byte("nonce-1"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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
		CommandId: "cmd-replay-3",
		HostId:    "host-1",
		Sequence:  7,
		Nonce:     []byte("nonce-3"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
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

func TestRejectsStaleIssuedAt(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	// issued_at = now - 2 hours (well beyond 2 * default_skew of 120s)
	staleIssuedAt := now.Add(-2 * time.Hour)
	fut := now.Add(5 * time.Minute)

	env := &pb.CommandEnvelope{
		CommandId: "cmd-stale",
		HostId:    "host-1",
		Sequence:  1,
		Nonce:     []byte("nonce-stale"),
		IssuedAt:  timestamppb.New(staleIssuedAt),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
	}

	canonBytes := canonicalBytesFn(env)
	sig := ed25519.Sign(priv, canonBytes)
	env.Signature = sig

	v := New(pub, []string{"shell.exec"}, "high")
	err = v.Accept(env, now)
	if err != ErrExpired {
		t.Errorf("Expected ErrExpired (stale issued_at), got %v", err)
	}
}

func TestAcceptsCurrentIssuedAt(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	now := time.Now()
	fut := now.Add(5 * time.Minute)

	env := &pb.CommandEnvelope{
		CommandId: "cmd-current",
		HostId:    "host-1",
		Sequence:  1,
		Nonce:     []byte("nonce-current"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_ShellExec{ShellExec: &pb.ShellExec{Command: "ls"}},
	}

	canonBytes := canonicalBytesFn(env)
	sig := ed25519.Sign(priv, canonBytes)
	env.Signature = sig

	v := New(pub, []string{"shell.exec"}, "high")
	err = v.Accept(env, now)
	if err != nil {
		t.Errorf("Accept with current IssuedAt failed: %v", err)
	}
}
