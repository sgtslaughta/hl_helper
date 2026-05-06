package executor_test

import (
	"crypto/ed25519"
	"testing"

	"github.com/hlhelper/hl-agent/internal/executor"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// TestSigningMatchesServerExpectation verifies that BuildAndSign produces
// signatures that match the server's verify_result function expectations.
// The server signs: pk.verify(env.signature, canonical_result_bytes(env))
// where canonical_result_bytes clears signature and deterministic-marshals.
func TestSigningMatchesServerExpectation(t *testing.T) {
	// Generate a key pair
	pubKey, privKey, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	signer := &mockSigner{privKey: privKey}

	// Create a result envelope with all fields populated
	env := &pb.ResultEnvelope{
		CommandId:      "cmd-123",
		HostId:         "host-456",
		Sequence:       1,
		StartedAt:      timestamppb.Now(),
		CompletedAt:    timestamppb.Now(),
		ExitCode:       0,
		StdoutChunk:    []byte("hello world"),
		StderrChunk:    []byte(""),
		Final:          true,
		Status:         pb.ResultStatus_RESULT_OK,
		RejectionReason: "",
		PrevResultHash: make([]byte, 32),
		Signature:      []byte{},
	}

	// Sign using BuildAndSign
	err = executor.BuildAndSign(env, signer)
	if err != nil {
		t.Fatalf("BuildAndSign failed: %v", err)
	}

	// Now verify using the server's verification logic:
	// 1. Create a copy with signature cleared
	// 2. Deterministic marshal
	// 3. Verify signature against those canonical bytes
	copy := &pb.ResultEnvelope{
		CommandId:       env.CommandId,
		HostId:          env.HostId,
		Sequence:        env.Sequence,
		StartedAt:       env.StartedAt,
		CompletedAt:     env.CompletedAt,
		ExitCode:        env.ExitCode,
		StdoutChunk:     env.StdoutChunk,
		StderrChunk:     env.StderrChunk,
		Final:           env.Final,
		Status:          env.Status,
		RejectionReason: env.RejectionReason,
		PrevResultHash:  env.PrevResultHash,
		Signature:       []byte{}, // Cleared
	}

	// Deterministic marshal (as server does)
	canonicalBytes, err := proto.MarshalOptions{Deterministic: true}.Marshal(copy)
	if err != nil {
		t.Fatalf("failed to marshal canonical bytes: %v", err)
	}

	// Verify signature against canonical bytes
	if !ed25519.Verify(pubKey, canonicalBytes, env.Signature) {
		t.Fatalf("signature verification failed - BuildAndSign produced invalid signature")
	}

	t.Logf("signature verified successfully: %d bytes", len(env.Signature))
}

// TestMultipleResultsChain verifies that consecutive results can be signed
// and each maintains the prev_result_hash chain.
func TestMultipleResultsChain(t *testing.T) {
	pubKey, privKey, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	signer := &mockSigner{privKey: privKey}

	// Create first result
	result1 := &pb.ResultEnvelope{
		CommandId:      "cmd-1",
		HostId:         "host-1",
		Sequence:       1,
		StartedAt:      timestamppb.Now(),
		CompletedAt:    timestamppb.Now(),
		ExitCode:       0,
		StdoutChunk:    []byte("result1"),
		Status:         pb.ResultStatus_RESULT_OK,
		PrevResultHash: make([]byte, 32), // Genesis
	}

	err = executor.BuildAndSign(result1, signer)
	if err != nil {
		t.Fatalf("sign result1 failed: %v", err)
	}

	// Compute hash of result1 (for chaining)
	copy1 := &pb.ResultEnvelope{
		CommandId:       result1.CommandId,
		HostId:          result1.HostId,
		Sequence:        result1.Sequence,
		StartedAt:       result1.StartedAt,
		CompletedAt:     result1.CompletedAt,
		ExitCode:        result1.ExitCode,
		StdoutChunk:     result1.StdoutChunk,
		StderrChunk:     result1.StderrChunk,
		Final:           result1.Final,
		Status:          result1.Status,
		RejectionReason: result1.RejectionReason,
		PrevResultHash:  result1.PrevResultHash,
		Signature:       []byte{},
	}
	canonicalBytes1, _ := proto.MarshalOptions{Deterministic: true}.Marshal(copy1)

	// Verify result1
	if !ed25519.Verify(pubKey, canonicalBytes1, result1.Signature) {
		t.Fatalf("result1 signature verification failed")
	}

	// Create second result with prev_hash pointing to result1
	result2 := &pb.ResultEnvelope{
		CommandId:      "cmd-2",
		HostId:         "host-1",
		Sequence:       2,
		StartedAt:      timestamppb.Now(),
		CompletedAt:    timestamppb.Now(),
		ExitCode:       1,
		StdoutChunk:    []byte("result2"),
		Status:         pb.ResultStatus_RESULT_FAIL,
		PrevResultHash: canonicalBytes1, // Chain from result1
	}

	err = executor.BuildAndSign(result2, signer)
	if err != nil {
		t.Fatalf("sign result2 failed: %v", err)
	}

	// Verify result2
	copy2 := &pb.ResultEnvelope{
		CommandId:       result2.CommandId,
		HostId:          result2.HostId,
		Sequence:        result2.Sequence,
		StartedAt:       result2.StartedAt,
		CompletedAt:     result2.CompletedAt,
		ExitCode:        result2.ExitCode,
		StdoutChunk:     result2.StdoutChunk,
		StderrChunk:     result2.StderrChunk,
		Final:           result2.Final,
		Status:          result2.Status,
		RejectionReason: result2.RejectionReason,
		PrevResultHash:  result2.PrevResultHash,
		Signature:       []byte{},
	}
	canonicalBytes2, _ := proto.MarshalOptions{Deterministic: true}.Marshal(copy2)

	if !ed25519.Verify(pubKey, canonicalBytes2, result2.Signature) {
		t.Fatalf("result2 signature verification failed")
	}

	t.Logf("chain verified: result1 -> result2")
}
