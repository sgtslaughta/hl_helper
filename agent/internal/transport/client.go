// Package transport runs the persistent agent -> server gRPC bidi stream.
package transport

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"errors"
	"fmt"
	"log"
	"math/rand"
	"os"
	"path/filepath"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/hlhelper/hl-agent/internal/executor"
	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/outbox"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

// Executor interface for running commands.
type Executor interface {
	Execute(ctx context.Context, cmd *pb.CommandEnvelope) *pb.ResultEnvelope
}

// Signer interface for signing results.
type Signer interface {
	Sign(msg []byte) ([]byte, error)
}

type Options struct {
	Endpoint          string
	HostID            string // sent in heartbeats; from manifest.json
	Keystore          keystore.Keystore
	Outbox            *outbox.Outbox
	Executor          Executor     // optional; if set, commands are executed and results signed
	Signer            Signer       // optional; used to sign results (defaults to keystore if not set)
	OnCommand         func(*pb.CommandEnvelope) // optional legacy callback
	BaseBackoff       time.Duration
	MaxBackoff        time.Duration
	HeartbeatInterval time.Duration // default 15s when zero
	DialOptions       []grpc.DialOption // override (tests use bufconn)
	KeystoreDir       string        // optional; for persisting result sequence counter
}

type Client struct{ opts Options }

func New(opts Options) *Client { return &Client{opts: opts} }

func (c *Client) Run(ctx context.Context) error {
	backoff := c.opts.BaseBackoff
	if backoff == 0 {
		backoff = time.Second
	}
	maxB := c.opts.MaxBackoff
	if maxB == 0 {
		maxB = 60 * time.Second
	}
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		err := c.runOnce(ctx)
		if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
			return err
		}
		if err == nil {
			backoff = c.opts.BaseBackoff
			continue
		}
		log.Printf("transport: stream error: %v (retrying in %s)", err, backoff)
		jitter := time.Duration(rand.Int63n(int64(backoff/4 + 1)))
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(backoff + jitter):
		}
		if backoff < maxB {
			backoff *= 2
			if backoff > maxB {
				backoff = maxB
			}
		}
	}
}

// RunOnce executes a single Stream RPC and processes incoming messages.
func (c *Client) RunOnce(ctx context.Context) error {
	return c.runOnce(ctx)
}

func (c *Client) runOnce(ctx context.Context) error {
	dialOpts := c.opts.DialOptions
	if dialOpts == nil {
		creds, err := c.tlsCreds()
		if err != nil {
			return err
		}
		dialOpts = []grpc.DialOption{grpc.WithTransportCredentials(creds)}
	}
	conn, err := grpc.NewClient(c.opts.Endpoint, dialOpts...)
	if err != nil {
		return err
	}
	defer conn.Close()
	stub := pb.NewAgentBridgeClient(conn)
	stream, err := stub.Stream(ctx)
	if err != nil {
		return err
	}

	hbInterval := c.opts.HeartbeatInterval
	if hbInterval <= 0 {
		hbInterval = 15 * time.Second
	}

	// gRPC bidi stream Send is NOT goroutine-safe. Serialize all senders
	// (heartbeat + outbox drain) through this mutex.
	var sendMu sync.Mutex
	sendMsg := func(msg *pb.AgentToServer) error {
		sendMu.Lock()
		defer sendMu.Unlock()
		return stream.Send(msg)
	}

	// Heartbeat sender goroutine. Lifecycle is bound to ctx + send-error.
	hbCtx, hbCancel := context.WithCancel(ctx)
	defer hbCancel()
	hbErr := make(chan error, 1)
	go func() {
		// Send one immediately on stream open so server registers the host
		// promptly (avoids ~15s of "offline" right after connect).
		if err := sendMsg(&pb.AgentToServer{
			Msg: &pb.AgentToServer_Heartbeat{
				Heartbeat: &pb.Heartbeat{
					HostId: c.opts.HostID,
					At:     timestamppb.Now(),
				},
			},
		}); err != nil {
			hbErr <- err
			return
		}
		t := time.NewTicker(hbInterval)
		defer t.Stop()
		for {
			select {
			case <-hbCtx.Done():
				return
			case <-t.C:
				if err := sendMsg(&pb.AgentToServer{
					Msg: &pb.AgentToServer_Heartbeat{
						Heartbeat: &pb.Heartbeat{
							HostId: c.opts.HostID,
							At:     timestamppb.Now(),
						},
					},
				}); err != nil {
					hbErr <- err
					return
				}
			}
		}
	}()

	// Load result sequence counter + previous canonical hash if executor is set
	var resultSeqMu sync.Mutex
	var resultSeq uint64 = 1
	prevHash := make([]byte, 32)
	if c.opts.Executor != nil && c.opts.KeystoreDir != "" {
		resultSeq = c.loadResultSequence()
		if h := c.loadResultPrevHash(); len(h) == 32 {
			prevHash = h
		}
	}

	// Outbox drain goroutine: periodically send pending results
	outboxErr := make(chan error, 1)
	if c.opts.Outbox != nil {
		go func() {
			ticker := time.NewTicker(1 * time.Second)
			defer ticker.Stop()
			for {
				select {
				case <-hbCtx.Done():
					return
				case <-ticker.C:
					entries, err := c.opts.Outbox.Peek(10)
					if err != nil {
						log.Printf("outbox peek error: %v", err)
						continue
					}
					if len(entries) > 0 {
						log.Printf("outbox: draining %d entries", len(entries))
					}
					for _, entry := range entries {
						// Unmarshal the result from outbox
						result := &pb.ResultEnvelope{}
						if err := proto.Unmarshal(entry.Payload, result); err != nil {
							log.Printf("failed to unmarshal result from outbox: %v", err)
							continue
						}
						if err := sendMsg(&pb.AgentToServer{
							Msg: &pb.AgentToServer_Result{
								Result: result,
							},
						}); err != nil {
							outboxErr <- err
							return
						}
						log.Printf("outbox: sent result id=%d cmd=%s", entry.ID, result.CommandId)
						if err := c.opts.Outbox.Ack(entry.ID); err != nil {
							log.Printf("outbox ack error for id %d: %v", entry.ID, err)
						}
					}
				}
			}
		}()
	}

	recvErr := make(chan error, 1)
	go func() {
		for {
			msg, e := stream.Recv()
			if e != nil {
				recvErr <- e
				return
			}
			if cmd := msg.GetCommand(); cmd != nil {
				// If executor is set, execute the command and queue result
				if c.opts.Executor != nil && c.opts.Outbox != nil {
					go c.executeAndQueueResult(ctx, cmd, &resultSeqMu, &resultSeq, &prevHash)
				}
				// Also call legacy OnCommand callback if set
				if c.opts.OnCommand != nil {
					c.opts.OnCommand(cmd)
				}
			}
		}
	}()

	select {
	case e := <-recvErr:
		return e
	case e := <-hbErr:
		return e
	case e := <-outboxErr:
		return e
	}
}

// loadResultSequence reads the last persisted result sequence from disk, or returns 1.
func (c *Client) loadResultSequence() uint64 {
	seqFile := filepath.Join(c.opts.KeystoreDir, "result.seq")
	data, err := os.ReadFile(seqFile)
	if err != nil {
		return 1 // Genesis: start at 1
	}
	if len(data) != 8 {
		return 1
	}
	return binary.BigEndian.Uint64(data)
}

// loadResultPrevHash reads the canonical hash of the last result we sent. Returns nil if absent.
func (c *Client) loadResultPrevHash() []byte {
	p := filepath.Join(c.opts.KeystoreDir, "result.prev_hash")
	data, err := os.ReadFile(p)
	if err != nil || len(data) != 32 {
		return nil
	}
	return data
}

// saveResultPrevHash persists the canonical hash of the last sent result.
func (c *Client) saveResultPrevHash(h []byte) error {
	p := filepath.Join(c.opts.KeystoreDir, "result.prev_hash")
	return os.WriteFile(p, h, 0600)
}

// saveResultSequence persists the current result sequence to disk.
func (c *Client) saveResultSequence(seq uint64) error {
	seqFile := filepath.Join(c.opts.KeystoreDir, "result.seq")
	buf := make([]byte, 8)
	binary.BigEndian.PutUint64(buf, seq)
	return os.WriteFile(seqFile, buf, 0600)
}

// executeAndQueueResult runs the executor, builds a signed result, and appends to outbox.
func (c *Client) executeAndQueueResult(ctx context.Context, cmd *pb.CommandEnvelope, seqMu *sync.Mutex, seqPtr *uint64, prevHashPtr *[]byte) {
	// Execute the command
	result := c.opts.Executor.Execute(ctx, cmd)

	// Set common fields
	result.CommandId = cmd.CommandId
	result.HostId = c.opts.HostID

	// Get and increment sequence + read prev hash atomically
	seqMu.Lock()
	seq := *seqPtr
	*seqPtr++
	prev := make([]byte, 32)
	copy(prev, *prevHashPtr)
	seqMu.Unlock()
	result.Sequence = seq
	result.PrevResultHash = prev

	// Set timestamps if not already set
	if result.StartedAt == nil {
		result.StartedAt = timestamppb.Now()
	}
	if result.CompletedAt == nil {
		result.CompletedAt = timestamppb.Now()
	}

	// Mark as final
	result.Final = true

	// Sign the result
	signer := c.opts.Signer
	if signer == nil {
		signer = c.opts.Keystore
	}
	if err := executor.BuildAndSign(result, signer); err != nil {
		log.Printf("failed to sign result for command %s: %v", cmd.CommandId, err)
		return
	}

	// Marshal to bytes and append to outbox
	resultBytes, err := marshal(result)
	if err != nil {
		log.Printf("failed to marshal result for command %s: %v", cmd.CommandId, err)
		return
	}

	_, err = c.opts.Outbox.Append(resultBytes)
	if err != nil {
		log.Printf("failed to append result to outbox for command %s: %v", cmd.CommandId, err)
		return
	}

	// Compute new prev_hash for chain link: sha256(canonical bytes of this result).
	// Canonical form clears signature; we reuse what BuildAndSign signs over by
	// re-marshalling deterministically with signature cleared.
	canonClone, _ := proto.Clone(result).(*pb.ResultEnvelope)
	canonClone.Signature = nil
	canonBytes, _ := proto.MarshalOptions{Deterministic: true}.Marshal(canonClone)
	newHash := sha256.Sum256(canonBytes)
	seqMu.Lock()
	*prevHashPtr = newHash[:]
	seqMu.Unlock()

	// Persist next seq + new prev hash so a restart picks up the chain.
	if c.opts.KeystoreDir != "" {
		if err := c.saveResultSequence(seq + 1); err != nil {
			log.Printf("failed to save result sequence: %v", err)
		}
		if err := c.saveResultPrevHash(newHash[:]); err != nil {
			log.Printf("failed to save prev hash: %v", err)
		}
	}

	log.Printf("queued result for command %s (seq %d, status %d)", cmd.CommandId, seq, result.Status)
}

// marshal encodes a ResultEnvelope to bytes using protobuf.
func marshal(result *pb.ResultEnvelope) ([]byte, error) {
	return proto.Marshal(result)
}

func (c *Client) tlsCreds() (credentials.TransportCredentials, error) {
	chain, key, err := c.opts.Keystore.TLSCertAndKey()
	if err != nil {
		return nil, fmt.Errorf("load tls cert+key: %w", err)
	}
	if len(chain) == 0 || len(key) == 0 {
		return nil, fmt.Errorf("transport: keystore has no TLS material — enroll first")
	}
	cert, err := tls.X509KeyPair(chain, key)
	if err != nil {
		return nil, fmt.Errorf("X509KeyPair: %w", err)
	}
	if cert.Leaf == nil && len(cert.Certificate) > 0 {
		if leaf, err := x509.ParseCertificate(cert.Certificate[0]); err == nil {
			cert.Leaf = leaf
			log.Printf("transport: loaded client cert subj=%q pubkey=%T sigAlgo=%s",
				leaf.Subject.String(), leaf.PublicKey, leaf.SignatureAlgorithm)
		}
	}
	rootPEM, err := c.opts.Keystore.RootCAPEM()
	if err != nil {
		return nil, fmt.Errorf("load root CA: %w", err)
	}
	pool := x509.NewCertPool()
	if rootPEM != nil {
		pool.AppendCertsFromPEM(rootPEM)
	}
	cfg := &tls.Config{
		Certificates: []tls.Certificate{cert},
		RootCAs:      pool,
		MinVersion:   tls.VersionTLS13,
		GetClientCertificate: func(req *tls.CertificateRequestInfo) (*tls.Certificate, error) {
			log.Printf(
				"transport: server requested client cert (sigSchemes=%v ackedAcceptableCAs=%d)",
				req.SignatureSchemes, len(req.AcceptableCAs),
			)
			return &cert, nil
		},
	}
	return credentials.NewTLS(cfg), nil
}
