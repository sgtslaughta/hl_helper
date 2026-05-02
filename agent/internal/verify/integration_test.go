package verify

import (
	"crypto/ed25519"
	"testing"
	"time"

	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/hlhelper/hl-agent/internal/manifest"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

// TestIntegrationManifestAndVerify tests manifest loading with verifier.
func TestIntegrationManifestAndVerify(t *testing.T) {
	// Create default manifest
	m := manifest.DefaultManifest()
	m.HostID = "host-test-1"
	m.MaxRisk = "medium"

	// Create verifier from manifest
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("GenerateKey failed: %v", err)
	}

	v := New(pub, m.AllowedActions, m.MaxRisk)

	// Create command with allowed action
	now := time.Now()
	fut := now.Add(5 * time.Minute)

	env := &pb.CommandEnvelope{
		CommandId: "cmd-int-1",
		HostId:    m.HostID,
		Sequence:  1,
		Nonce:     []byte("nonce-int-1"),
		IssuedAt:  timestamppb.New(now),
		ExpiresAt: timestamppb.New(fut),
		IssuedBy:  "server",
		Risk:      pb.RiskLevel_RISK_LOW,
		Capability: &pb.CapabilityToken{},
		Payload:   &pb.CommandEnvelope_PkgUpdate{PkgUpdate: &pb.PkgUpdate{}},
	}

	canonicalBytes := canonicalMsg(env)
	sig := ed25519.Sign(priv, canonicalBytes)
	env.Signature = sig

	// Should accept
	if err := v.Accept(env, now); err != nil {
		t.Errorf("Accept should succeed, got %v", err)
	}
}
