// Package verify gates incoming commands by signature, manifest, and replay state.
package verify

import (
	"crypto/ed25519"
	"encoding/hex"
	"errors"
	"sync"
	"time"

	"google.golang.org/protobuf/proto"

	"github.com/hlhelper/hl-agent/internal/manifest"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

var (
	ErrBadSignature     = errors.New("verify: bad signature")
	ErrActionNotAllowed = errors.New("verify: action not allowed by manifest")
	ErrRiskTooHigh      = errors.New("verify: risk above manifest threshold")
	ErrReplay           = errors.New("verify: replay or stale sequence")
	ErrExpired          = errors.New("verify: command expired")
)

// Verifier gates incoming commands by signature, manifest, and replay state.
type Verifier struct {
	serverPub  ed25519.PublicKey
	allowed    map[string]bool
	maxRisk    int
	skewS      int
	mu         sync.Mutex
	lastSeq    uint64
	seenNonces map[string]struct{}
	nonceCap   int
}

// Option configures a Verifier.
type Option func(*Verifier)

// WithSkew sets the clock skew tolerance in seconds (default 60).
func WithSkew(seconds int) Option {
	return func(v *Verifier) {
		v.skewS = seconds
	}
}

// WithNonceCap sets the LRU nonce cache capacity (default 10000).
func WithNonceCap(cap int) Option {
	return func(v *Verifier) {
		v.nonceCap = cap
	}
}

// New creates a new Verifier.
func New(serverPub ed25519.PublicKey, allowedActions []string, maxRisk string, opts ...Option) *Verifier {
	allowed := make(map[string]bool)
	for _, a := range allowedActions {
		allowed[a] = true
	}

	v := &Verifier{
		serverPub:  serverPub,
		allowed:    allowed,
		maxRisk:    manifest.RiskLevel(maxRisk),
		skewS:      60,
		lastSeq:    0,
		seenNonces: make(map[string]struct{}),
		nonceCap:   10000,
	}

	for _, opt := range opts {
		opt(v)
	}

	return v
}

// Accept verifies an incoming command envelope and updates replay state.
// Returns nil if the command is valid and should be processed.
func (v *Verifier) Accept(env *pb.CommandEnvelope, now time.Time) error {
	v.mu.Lock()
	defer v.mu.Unlock()

	// 1. Verify signature
	if err := v.verifySignature(env); err != nil {
		return err
	}

	// 2. Map oneof to action string and check allowed
	action := payloadAction(env)
	if action == "" {
		return ErrActionNotAllowed
	}

	if !v.allowed[action] {
		return ErrActionNotAllowed
	}

	// 3. Check risk; map proto RiskLevel (0-2) to manifest level (0-3)
	// Proto: RISK_LOW=0, RISK_MED=1, RISK_HIGH=2
	// Manifest: low=0, medium=1, high=2, critical=3
	riskLevel := int(env.Risk)
	if riskLevel > v.maxRisk {
		return ErrRiskTooHigh
	}

	// 4. Check expiration
	if env.ExpiresAt != nil && env.ExpiresAt.AsTime().Before(now) {
		return ErrExpired
	}

	// 5. Check issued_at (clock skew)
	if env.IssuedAt != nil && env.IssuedAt.AsTime().After(now.Add(time.Duration(v.skewS)*time.Second)) {
		return ErrExpired
	}

	// 6. Check sequence
	if env.Sequence <= v.lastSeq {
		return ErrReplay
	}
	v.lastSeq = env.Sequence

	// 7. Check nonce
	nonceHex := hex.EncodeToString(env.Nonce)
	if _, seen := v.seenNonces[nonceHex]; seen {
		return ErrReplay
	}

	// Add nonce, evict if necessary
	v.seenNonces[nonceHex] = struct{}{}
	if len(v.seenNonces) > v.nonceCap {
		// Simple eviction: remove first entry found
		for k := range v.seenNonces {
			delete(v.seenNonces, k)
			break
		}
	}

	return nil
}

// verifySignature verifies the Ed25519 signature on the envelope.
func (v *Verifier) verifySignature(env *pb.CommandEnvelope) error {
	// Compute canonical bytes (copy without signature)
	copy := *env
	copy.Signature = nil

	msg := canonicalMsg(&copy)

	if !ed25519.Verify(v.serverPub, msg, env.Signature) {
		return ErrBadSignature
	}

	return nil
}

// canonicalMsg produces a deterministic byte representation of the envelope.
// This must match the server's signing logic.
func canonicalMsg(env *pb.CommandEnvelope) []byte {
	cp := proto.Clone(env).(*pb.CommandEnvelope)
	cp.Signature = nil
	data, _ := proto.MarshalOptions{Deterministic: true}.Marshal(cp)
	return data
}

// payloadAction extracts and normalizes the payload action name.
func payloadAction(env *pb.CommandEnvelope) string {
	switch env.Payload.(type) {
	case *pb.CommandEnvelope_PkgUpdate:
		return "pkg.update"
	case *pb.CommandEnvelope_Reboot:
		return "reboot"
	case *pb.CommandEnvelope_ShellExec:
		return "shell.exec"
	case *pb.CommandEnvelope_GetFacts:
		return "get_facts"
	case *pb.CommandEnvelope_DockerOp:
		return "docker.op"
	case *pb.CommandEnvelope_PluginInvoke:
		return "plugin.invoke"
	case *pb.CommandEnvelope_TerminalOpen:
		return "terminal.open"
	case *pb.CommandEnvelope_FileTransfer:
		return "file.transfer"
	default:
		return ""
	}
}
