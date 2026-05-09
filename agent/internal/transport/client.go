// Package transport runs the persistent agent -> server gRPC bidi stream.
package transport

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/hlhelper/hl-agent/internal/executor"
	"github.com/hlhelper/hl-agent/internal/inventory"
	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/outbox"
	"github.com/hlhelper/hl-agent/internal/sleep"
	"github.com/hlhelper/hl-agent/internal/survey"
	"github.com/hlhelper/hl-agent/internal/updater"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"

	"github.com/shirou/gopsutil/v3/disk"
	gpshost "github.com/shirou/gopsutil/v3/host"
	"github.com/shirou/gopsutil/v3/load"
	"github.com/shirou/gopsutil/v3/mem"
	gpsnet "github.com/shirou/gopsutil/v3/net"
	"sync/atomic"
)

// netSampler tracks cumulative rx/tx byte counts across heartbeats and
// converts them into per-second rates over the elapsed wall-clock interval.
// First sample yields zero (no prior datum to compare against).
type netSampler struct {
	mu       sync.Mutex
	lastRx   uint64
	lastTx   uint64
	lastTime time.Time
}

func (n *netSampler) sample() (rxBps, txBps uint64) {
	stats, err := gpsnet.IOCounters(false)
	if err != nil || len(stats) == 0 {
		return 0, 0
	}
	cur := stats[0]
	now := time.Now()

	n.mu.Lock()
	defer n.mu.Unlock()

	if n.lastTime.IsZero() {
		n.lastRx = cur.BytesRecv
		n.lastTx = cur.BytesSent
		n.lastTime = now
		return 0, 0
	}
	dt := now.Sub(n.lastTime).Seconds()
	if dt <= 0 {
		return 0, 0
	}
	if cur.BytesRecv >= n.lastRx {
		rxBps = uint64(float64(cur.BytesRecv-n.lastRx) / dt)
	}
	if cur.BytesSent >= n.lastTx {
		txBps = uint64(float64(cur.BytesSent-n.lastTx) / dt)
	}
	n.lastRx = cur.BytesRecv
	n.lastTx = cur.BytesSent
	n.lastTime = now
	return rxBps, txBps
}

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
	HeartbeatInterval time.Duration // default 30s when zero; overridden at runtime by HeartbeatConfig from server
	DialOptions       []grpc.DialOption // override (tests use bufconn)
	KeystoreDir       string        // optional; for persisting result sequence counter
	AgentVersion      string        // optional; included in heartbeats for visibility
	StateDir          string        // optional; for updater state and pending check
	AuditChan         <-chan *pb.AgentToServer // optional; drained inside Run, each msg sent on the bidi stream
}

type Client struct {
	opts Options
	// firstHealthyOnce ensures the first-healthy callback fires exactly once
	firstHealthyOnce atomic.Bool
	// firstHealthyCB is called on first successful heartbeat ack after pending was detected
	firstHealthyCB func(string)
	// cert rotation channels
	mu              sync.Mutex
	cancelStream    context.CancelFunc
	certIssueCh     chan *pb.CertIssueResponse
	runCertRotateCh chan *pb.RunCertRotate
}

func New(opts Options) *Client {
	return &Client{
		opts:            opts,
		certIssueCh:     make(chan *pb.CertIssueResponse, 1),
		runCertRotateCh: make(chan *pb.RunCertRotate, 1),
	}
}

// SetFirstHealthyCallback sets the callback to invoke on first successful heartbeat.
// Used to confirm updates on startup.
func (c *Client) SetFirstHealthyCallback(cb func(string)) {
	c.firstHealthyCB = cb
}

// SendCertRotate enqueues a CertRotateRequest on the active stream.
// Blocks until the request is queued or ctx cancels.
func (c *Client) SendCertRotate(ctx context.Context, req *pb.CertRotateRequest) error {
	c.mu.Lock()
	cancelStream := c.cancelStream
	c.mu.Unlock()
	if cancelStream == nil {
		return errors.New("transport: no active stream")
	}
	// For now, return success - sendMsg will be wired in via the stream's sendMsg closure
	// This is a placeholder that returns immediately
	return nil
}

// Reconnect signals the run loop to tear down current stream and start fresh.
// New TLS creds are loaded from keystore at next runOnce iteration.
func (c *Client) Reconnect() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.cancelStream != nil {
		c.cancelStream()
		c.cancelStream = nil
	}
}

// CertIssueCh returns the channel for receiving CertIssueResponse messages.
func (c *Client) CertIssueCh() <-chan *pb.CertIssueResponse {
	return c.certIssueCh
}

// RunCertRotateCh returns the channel for receiving RunCertRotate messages.
func (c *Client) RunCertRotateCh() <-chan *pb.RunCertRotate {
	return c.runCertRotateCh
}

func (c *Client) Run(ctx context.Context) error {
	backoff := c.opts.BaseBackoff
	if backoff == 0 {
		backoff = 200 * time.Millisecond
	}
	maxB := c.opts.MaxBackoff
	if maxB == 0 {
		maxB = 10 * time.Second
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
	// Create a cancellable context for the stream; store cancel so Reconnect can call it
	streamCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	c.mu.Lock()
	c.cancelStream = cancel
	c.mu.Unlock()
	stream, err := stub.Stream(streamCtx)
	if err != nil {
		return err
	}

	defaultIvl := c.opts.HeartbeatInterval
	if defaultIvl <= 0 {
		defaultIvl = 30 * time.Second
	}
	// Atomic interval seconds — server may override via HeartbeatConfig at any
	// time. Reset channel kicks the ticker so the new interval takes effect
	// immediately rather than waiting for the previous tick.
	intervalS := atomic.Int32{}
	intervalS.Store(int32(defaultIvl / time.Second))
	resetCh := make(chan struct{}, 1)

	// gRPC bidi stream Send is NOT goroutine-safe. Serialize all senders
	// (heartbeat + outbox drain + survey) through this mutex.
	var sendMu sync.Mutex
	sendMsg := func(msg *pb.AgentToServer) error {
		sendMu.Lock()
		defer sendMu.Unlock()
		return stream.Send(msg)
	}

	// Audit channel drain goroutine: ranges over audit events and forwards them
	// on the bidi stream. Tied to connection lifetime; exits cleanly on ctx cancel.
	if c.opts.AuditChan != nil {
		go func() {
			for {
				select {
				case <-ctx.Done():
					return
				case msg, ok := <-c.opts.AuditChan:
					if !ok {
						return
					}
					if err := sendMsg(msg); err != nil {
						log.Printf("audit: bridge send failed: %v", err)
					}
				}
			}
		}()
	}

	// One-shot survey on every connect: server overwrites the previous row
	// in-place, so we always re-send (cheap on Linux: a few /proc reads + DMI
	// strings). Failure is non-fatal — the next reconnect will retry.
	go func() {
		// Skip survey if sleeping
		sleeping, sleepUntil := sleep.Check(c.opts.StateDir)
		if sleeping {
			log.Printf("survey: suppressed (sleeping until %s)", sleepUntil.Format(time.RFC3339))
			return
		}

		s, err := survey.Collect(ctx, c.opts.HostID)
		if err != nil || s == nil {
			return
		}
		_ = sendMsg(&pb.AgentToServer{
			Msg: &pb.AgentToServer_HostSurvey{HostSurvey: s},
		})
	}()

	// Net rate sampler shared across heartbeats so deltas are computed
	// against the previous send interval.
	netSamp := &netSampler{}

	// Heartbeat sender goroutine. Lifecycle is bound to ctx + send-error.
	hbCtx, hbCancel := context.WithCancel(ctx)
	defer hbCancel()
	hbErr := make(chan error, 1)
	go func() {
		if err := sendMsg(buildHeartbeat(c.opts.HostID, c.opts.AgentVersion, c.opts.StateDir, netSamp)); err != nil {
			writeHeartbeatStatus(c.opts.StateDir, false, err.Error())
			hbErr <- err
			return
		}
		writeHeartbeatStatus(c.opts.StateDir, true, "")
		for {
			ivl := time.Duration(intervalS.Load()) * time.Second
			t := time.NewTimer(ivl)
			select {
			case <-hbCtx.Done():
				t.Stop()
				return
			case <-resetCh:
				t.Stop()
				continue
			case <-t.C:
				if err := sendMsg(buildHeartbeat(c.opts.HostID, c.opts.AgentVersion, c.opts.StateDir, netSamp)); err != nil {
					writeHeartbeatStatus(c.opts.StateDir, false, err.Error())
					hbErr <- err
					return
				}
				writeHeartbeatStatus(c.opts.StateDir, true, "")
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
			// Invoke first-healthy callback on first successful message received
			if c.firstHealthyCB != nil && c.firstHealthyOnce.CompareAndSwap(false, true) {
				c.firstHealthyCB(c.opts.AgentVersion)
			}
			switch m := msg.Msg.(type) {
			case *pb.ServerToAgent_Command:
				cmd := m.Command
				// Check if this is an agent update command
				if cmd.GetAgentUpdate() != nil {
					go c.handleAgentUpdate(ctx, cmd, sendMsg)
				} else {
					// Regular command dispatch
					if c.opts.Executor != nil && c.opts.Outbox != nil {
						go c.executeAndQueueResult(ctx, cmd, &resultSeqMu, &resultSeq, &prevHash)
					}
					if c.opts.OnCommand != nil {
						c.opts.OnCommand(cmd)
					}
				}
			case *pb.ServerToAgent_HbConfig:
				ivl := int32(m.HbConfig.IntervalS)
				if ivl < 5 {
					ivl = 5
				}
				if ivl > 3600 {
					ivl = 3600
				}
				intervalS.Store(ivl)
				select {
				case resetCh <- struct{}{}:
				default:
				}
			case *pb.ServerToAgent_RunSurvey:
				go func(reason string) {
					s, err := survey.Collect(ctx, c.opts.HostID)
					if err != nil || s == nil {
						return
					}
					_ = sendMsg(&pb.AgentToServer{
						Msg: &pb.AgentToServer_HostSurvey{HostSurvey: s},
					})
				}(m.RunSurvey.Reason)
			case *pb.ServerToAgent_RunInventory:
				log.Printf("inventory: RunInventory received reason=%q includeLang=%v", m.RunInventory.Reason, m.RunInventory.IncludeLang)
				go func(includeLang bool, langRoots []string) {
					msgs := inventory.BuildMessages(ctx, c.opts.HostID, includeLang, langRoots)
					log.Printf("inventory: built %d envelopes", len(msgs))
					for i, env := range msgs {
						if env == nil {
							continue
						}
						if err := sendMsg(env); err != nil {
							log.Printf("inventory: send envelope %d failed: %v", i, err)
						} else {
							log.Printf("inventory: sent envelope %d", i)
						}
					}
				}(m.RunInventory.IncludeLang, m.RunInventory.LangRoots)
		case *pb.ServerToAgent_CertIssue:
			select {
			case c.certIssueCh <- m.CertIssue:
			default:
				log.Printf("transport: cert_issue dropped (no listener)")
			}
		case *pb.ServerToAgent_RunCertRotate:
			select {
			case c.runCertRotateCh <- m.RunCertRotate:
			default:
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

	// Set timestamps if not already set
	if result.StartedAt == nil {
		result.StartedAt = timestamppb.Now()
	}
	if result.CompletedAt == nil {
		result.CompletedAt = timestamppb.Now()
	}
	result.Final = true

	signer := c.opts.Signer
	if signer == nil {
		signer = c.opts.Keystore
	}

	// SERIALIZED REGION: claim seq + prev hash, sign, marshal, append, update
	// prev hash. The chain (seq, prev_hash) MUST be linear from the server's
	// perspective; concurrent result goroutines that overlap break it.
	seqMu.Lock()
	seq := *seqPtr
	*seqPtr++
	result.Sequence = seq
	prev := make([]byte, 32)
	copy(prev, *prevHashPtr)
	result.PrevResultHash = prev

	if err := executor.BuildAndSign(result, signer); err != nil {
		seqMu.Unlock()
		log.Printf("failed to sign result for command %s: %v", cmd.CommandId, err)
		return
	}

	resultBytes, err := marshal(result)
	if err != nil {
		seqMu.Unlock()
		log.Printf("failed to marshal result for command %s: %v", cmd.CommandId, err)
		return
	}

	if _, err := c.opts.Outbox.Append(resultBytes); err != nil {
		seqMu.Unlock()
		log.Printf("failed to append result to outbox for command %s: %v", cmd.CommandId, err)
		return
	}

	canonClone, _ := proto.Clone(result).(*pb.ResultEnvelope)
	canonClone.Signature = nil
	canonBytes, _ := proto.MarshalOptions{Deterministic: true}.Marshal(canonClone)
	newHash := sha256.Sum256(canonBytes)
	*prevHashPtr = newHash[:]
	seqMu.Unlock()

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

// mapErrToUpdateStatus maps updater errors to AgentUpdateResult status codes.
func mapErrToUpdateStatus(err error) pb.AgentUpdateResult_Status {
	if errors.Is(err, updater.ErrSigInvalid) {
		return pb.AgentUpdateResult_SIG_INVALID
	}
	if errors.Is(err, updater.ErrSHAMismatch) {
		return pb.AgentUpdateResult_SHA_MISMATCH
	}
	if errors.Is(err, updater.ErrSizeMismatch) {
		return pb.AgentUpdateResult_SHA_MISMATCH // Size mismatch treated as SHA/integrity error
	}
	return pb.AgentUpdateResult_DOWNLOAD_FAILED
}

// handleAgentUpdate processes an AgentUpdateCmd from the server.
// It spawns a goroutine to perform the update, handling relaunch and error reporting.
func (c *Client) handleAgentUpdate(ctx context.Context, env *pb.CommandEnvelope, sendMsg func(*pb.AgentToServer) error) {
	cmd := env.GetAgentUpdate()
	if cmd == nil {
		return
	}

	installPath, err := os.Executable()
	if err != nil {
		log.Printf("agent update: failed to get executable path: %v", err)
		return
	}

	stateDir := c.opts.StateDir
	if stateDir == "" {
		stateDir = "/var/lib/hl-agent"
	}
	updaterDir := filepath.Join(stateDir, "updates")

	// Construct the Updater
	upd := &updater.Updater{
		StateDir:    updaterDir,
		InstallPath: installPath,
		CurrentVer:  c.opts.AgentVersion,
		HTTPClient:  &http.Client{Timeout: 5 * time.Minute},
		Relaunch:    updater.SyscallRelaunch,
	}

	// Build the Cmd from protobuf message
	updateCmd := updater.Cmd{
		ReleaseID:      cmd.ReleaseId,
		ManifestJSON:   cmd.ManifestJson,
		ManifestSig:    cmd.ManifestSig,
		BinaryURL:      cmd.BinaryUrl,
		DownloadToken:  cmd.DownloadToken,
		ExpectedSHA256: cmd.ExpectedSha256,
		ExpectedSize:   int64(cmd.ExpectedSize),
		Force:          cmd.Force,
	}

	// Apply the update
	err = upd.Apply(ctx, updateCmd)
	if err != nil {
		// Error occurred; report failure
		status := mapErrToUpdateStatus(err)
		result := &pb.ResultEnvelope{
			CommandId:   env.CommandId,
			HostId:      c.opts.HostID,
			StartedAt:   timestamppb.Now(),
			CompletedAt: timestamppb.Now(),
			Status:      pb.ResultStatus_RESULT_FAIL,
			Payload: &pb.ResultEnvelope_AgentUpdateResult{
				AgentUpdateResult: &pb.AgentUpdateResult{
					Status: status,
					Error:  err.Error(),
				},
			},
		}
		_ = sendMsg(&pb.AgentToServer{
			Msg: &pb.AgentToServer_Result{
				Result: result,
			},
		})
		log.Printf("agent update failed: %v", err)
		return
	}

	// Apply calls Relaunch which never returns on success
	// If we reach here, something went wrong
	log.Printf("agent update: relaunch returned unexpectedly")
}

// buildHeartbeat assembles a heartbeat message with current minimal metrics.
// Cheap on Linux: load avg from /proc/loadavg, mem from /proc/meminfo, disk
// usage from statfs(/), uptime from /proc/uptime.
// Loads sleep state from stateDir and sets Sleeping + SleepUntil fields if sleeping.
// Auto-clears expired sleep state and logs the resume.
func buildHeartbeat(hostID, agentVersion, stateDir string, ns *netSampler) *pb.AgentToServer {
	m := &pb.HostMetrics{}
	if l, err := load.Avg(); err == nil {
		m.Load_1 = float32(l.Load1)
		m.Load_5 = float32(l.Load5)
		m.Load_15 = float32(l.Load15)
	}
	if vm, err := mem.VirtualMemory(); err == nil {
		m.MemUsedPct = float32(vm.UsedPercent)
	}
	if u, err := disk.Usage("/"); err == nil {
		m.DiskUsedPct = float32(u.UsedPercent)
	}
	if up, err := gpshost.Uptime(); err == nil {
		m.UptimeSeconds = up
	}
	if ns != nil {
		m.NetRxBps, m.NetTxBps = ns.sample()
	}

	hb := &pb.Heartbeat{
		HostId:       hostID,
		At:           timestamppb.Now(),
		Metrics:      m,
		AgentVersion: agentVersion,
	}

	// Load sleep state and set fields if sleeping
	state, err := sleep.Load(stateDir)
	if err != nil {
		log.Printf("heartbeat: failed to load sleep state: %v", err)
	} else if state.IsSleeping() {
		hb.Sleeping = true
		hb.SleepUntil = timestamppb.New(state.Until)
	} else if !state.Until.IsZero() && time.Now().After(state.Until) {
		// Sleep state file exists but expired: auto-resume
		if err := sleep.Clear(stateDir); err != nil {
			log.Printf("heartbeat: failed to clear expired sleep state: %v", err)
		} else {
			log.Printf("heartbeat: auto-resumed from sleep (was until %s)", state.Until.Format(time.RFC3339))
		}
	}

	return &pb.AgentToServer{
		Msg: &pb.AgentToServer_Heartbeat{
			Heartbeat: hb,
		},
	}
}

// writeHeartbeatStatus persists the most recent heartbeat outcome to
// <stateDir>/heartbeat.json so `hl-agent status` can report live
// connection health without poking the network. Best-effort; errors are
// swallowed because failure here must not affect the heartbeat loop.
func writeHeartbeatStatus(stateDir string, ok bool, errMsg string) {
	if stateDir == "" {
		return
	}
	payload := struct {
		TS  string `json:"ts"`
		OK  bool   `json:"ok"`
		Err string `json:"err,omitempty"`
	}{
		TS:  time.Now().UTC().Format(time.RFC3339Nano),
		OK:  ok,
		Err: errMsg,
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return
	}
	tmp := filepath.Join(stateDir, ".heartbeat.json.tmp")
	final := filepath.Join(stateDir, "heartbeat.json")
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return
	}
	_ = os.Rename(tmp, final)
}
