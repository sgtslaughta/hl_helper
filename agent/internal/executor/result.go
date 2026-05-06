package executor

import (
	"fmt"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
	"google.golang.org/protobuf/proto"
)

// Signer interface for signing result envelopes.
type Signer interface {
	Sign(msg []byte) ([]byte, error)
}

// BuildAndSign signs a ResultEnvelope using deterministic protobuf marshaling.
// Clears the signature field, marshals deterministically, signs the canonical bytes,
// and sets env.Signature. Returns error if signing fails.
func BuildAndSign(env *pb.ResultEnvelope, signer Signer) error {
	// Clear the signature field
	env.Signature = []byte{}

	// Deterministic marshal
	canonicalBytes, err := proto.MarshalOptions{Deterministic: true}.Marshal(env)
	if err != nil {
		return fmt.Errorf("failed to marshal envelope: %w", err)
	}

	// Sign the canonical bytes
	signature, signErr := signer.Sign(canonicalBytes)
	if signErr != nil {
		return fmt.Errorf("signing failed: %w", signErr)
	}

	// Set the signature
	env.Signature = signature

	return nil
}
