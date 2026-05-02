// Package verify gates incoming commands by signature, manifest, and replay state.
package verify

import (
	"crypto/ed25519"
	"encoding/hex"
	"errors"
	"sync"
	"time"

	"github.com/hlhelper/hl-agent/internal/manifest"
	pb "github.com/hlhelper/hl-agent/internal/transport/pb"
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
	action := env.WhichPayload()
	if action == "" {
		return ErrActionNotAllowed
	}

	actionMap := map[string]string{
		"pkg_update":    "pkg.update",
		"reboot":        "reboot",
		"shell_exec":    "shell.exec",
		"get_facts":     "get_facts",
		"docker_op":     "docker.op",
		"plugin_invoke": "plugin.invoke",
		"terminal_open": "terminal.open",
		"file_transfer": "file.transfer",
	}

	mappedAction, ok := actionMap[action]
	if !ok || !v.allowed[mappedAction] {
		return ErrActionNotAllowed
	}

	// 3. Check risk
	riskLevel := int(env.Risk)
	if riskLevel > v.maxRisk {
		return ErrRiskTooHigh
	}

	// 4. Check expiration
	if env.ExpiresAt != nil && env.ExpiresAt.Before(now) {
		return ErrExpired
	}

	// 5. Check issued_at (clock skew)
	if env.IssuedAt != nil && env.IssuedAt.After(now.Add(time.Duration(v.skewS)*time.Second)) {
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
	var buf []byte

	// Simple serialization: command_id, host_id, sequence, nonce, issued_at, expires_at, issued_by, risk, payload
	buf = append(buf, []byte(env.CommandID)...)
	buf = append(buf, 0)
	buf = append(buf, []byte(env.HostID)...)
	buf = append(buf, 0)

	// Sequence as little-endian uint64
	for i := 0; i < 8; i++ {
		buf = append(buf, byte(env.Sequence>>(uint(i)*8)))
	}

	buf = append(buf, env.Nonce...)
	buf = append(buf, 0)

	if env.IssuedAt != nil {
		t := env.IssuedAt.UnixNano()
		for i := 0; i < 8; i++ {
			buf = append(buf, byte(t>>(uint(i)*8)))
		}
	}

	if env.ExpiresAt != nil {
		t := env.ExpiresAt.UnixNano()
		for i := 0; i < 8; i++ {
			buf = append(buf, byte(t>>(uint(i)*8)))
		}
	}

	buf = append(buf, []byte(env.IssuedBy)...)
	buf = append(buf, 0)

	// Risk as int32
	risk := int32(env.Risk)
	for i := 0; i < 4; i++ {
		buf = append(buf, byte(risk>>(uint(i)*8)))
	}

	// Payload discriminator and basic data
	switch {
	case env.PkgUpdate != nil:
		buf = append(buf, []byte("pkg_update")...)
	case env.Reboot != nil:
		buf = append(buf, []byte("reboot")...)
	case env.ShellExec != nil:
		buf = append(buf, []byte("shell_exec")...)
		buf = append(buf, []byte(env.ShellExec.Command)...)
	case env.TerminalOpen != nil:
		buf = append(buf, []byte("terminal_open")...)
	case env.FileTransfer != nil:
		buf = append(buf, []byte("file_transfer")...)
	case env.DockerOp != nil:
		buf = append(buf, []byte("docker_op")...)
	case env.GetFacts != nil:
		buf = append(buf, []byte("get_facts")...)
	case env.PluginInvoke != nil:
		buf = append(buf, []byte("plugin_invoke")...)
		buf = append(buf, env.PluginInvoke.Payload...)
	}

	return buf
}
