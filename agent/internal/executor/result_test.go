package executor_test

import (
	"crypto/ed25519"
	"testing"

	"github.com/hlhelper/hl-agent/internal/executor"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type mockSigner struct {
	privKey ed25519.PrivateKey
}

func (m *mockSigner) Sign(msg []byte) ([]byte, error) {
	return ed25519.Sign(m.privKey, msg), nil
}

func TestBuildAndSign(t *testing.T) {
	// Generate a test key pair
	pubKey, privKey, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	signer := &mockSigner{privKey: privKey}

	// Create a test ResultEnvelope
	env := &pb.ResultEnvelope{
		CommandId:      "test-cmd-1",
		HostId:         "test-host-1",
		Sequence:       1,
		StartedAt:      timestamppb.Now(),
		CompletedAt:    timestamppb.Now(),
		ExitCode:       0,
		StdoutChunk:    []byte("hello"),
		StderrChunk:    []byte(""),
		Final:          true,
		Status:         pb.ResultStatus_RESULT_OK,
		RejectionReason: "",
		PrevResultHash: make([]byte, 32), // Genesis: all zeros
		Signature:      []byte{},          // Will be filled in
	}

	// Sign it
	err = executor.BuildAndSign(env, signer)
	if err != nil {
		t.Fatalf("BuildAndSign failed: %v", err)
	}

	// Verify signature is not empty
	if len(env.Signature) == 0 {
		t.Fatalf("signature is empty after BuildAndSign")
	}

	// Verify the signature is 64 bytes (Ed25519 signature)
	if len(env.Signature) != 64 {
		t.Fatalf("expected 64-byte signature, got %d", len(env.Signature))
	}

	// Verify signature by reconstructing canonical bytes and checking manually
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
		Signature:       []byte{},
	}

	canonicalBytes := canonicalResultBytes(copy)
	if !ed25519.Verify(pubKey, canonicalBytes, env.Signature) {
		t.Fatalf("signature verification failed")
	}
}

// Mirror of the server-side function for testing
func canonicalResultBytes(env *pb.ResultEnvelope) []byte {
	b, _ := proto.MarshalOptions{Deterministic: true}.Marshal(env)
	return b
}
