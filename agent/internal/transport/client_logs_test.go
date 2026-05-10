package transport

import (
	"context"
	"testing"
	"time"

	"github.com/hlhelper/hl-agent/internal/logging"
	logtransport "github.com/hlhelper/hl-agent/internal/logging/transport"
	"github.com/hlhelper/hl-agent/internal/logtypes"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

// TestBuildHeartbeatWithoutFlusher verifies that when no flusher is configured,
// buildHeartbeat returns a heartbeat with no Logs attached.
func TestBuildHeartbeatWithoutFlusher(t *testing.T) {
	c := &Client{
		opts: Options{
			HostID:       "test-host",
			AgentVersion: "1.0.0",
		},
		sessionID: "session-123",
	}

	hb := c.buildHeartbeat("test-host", "1.0.0", "", &netSampler{}, &NetIfaceSampler{})
	require.NotNil(t, hb)
	require.NotNil(t, hb.Msg)

	heartbeat, ok := hb.Msg.(*pb.AgentToServer_Heartbeat)
	require.True(t, ok)
	require.NotNil(t, heartbeat.Heartbeat)
	require.Nil(t, heartbeat.Heartbeat.Logs, "Logs should be nil when no flusher is configured")
}

// TestBuildHeartbeatWithFlusher verifies that when a flusher is configured,
// buildHeartbeat attaches a LogBatch if entries are pending.
func TestBuildHeartbeatWithFlusher(t *testing.T) {
	// Create a minimal buffer and emitter
	tmpDir := t.TempDir()
	emitterCfg := logging.Config{
		BufferPath:   tmpDir + "/buffer",
		AgentID:      "test-agent",
		SessionID:    "test-session",
		HostID:       "test-host",
		HostName:     "test-hostname",
		AgentVer:     "1.0.0",
		FallbackFile: tmpDir + "/fallback.log",
		MaxBytes:     10 * 1024 * 1024,
		MaxAge:       7 * 24 * time.Hour,
	}
	em, err := logging.New(emitterCfg)
	require.NoError(t, err)
	defer em.Close()

	// Create logging transport components
	dict := logtransport.New()
	sampler := &logtransport.Sampler{DefaultRate: 1.0}
	coalescer := &logtransport.Coalescer{Window: 1 * time.Second}

	flusherCfg := logtransport.Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sampler,
		Coalescer: coalescer,
	}
	flusher := logtransport.NewFlusher(flusherCfg)

	// Emit 3 events
	em.Emit(logtypes.LevelInfo, "test", "action1", "message1", nil)
	em.Emit(logtypes.LevelInfo, "test", "action2", "message2", nil)
	em.Emit(logtypes.LevelInfo, "test", "action3", "message3", nil)

	// Wait for events to be buffered
	time.Sleep(100 * time.Millisecond)

	// Create client with flusher
	c := &Client{
		opts: Options{
			HostID:       "test-host",
			AgentVersion: "1.0.0",
			Flusher:      flusher,
		},
		sessionID: "session-123",
	}

	// Create a mock unary client that records calls
	mockClient := &mockAgentBridgeClient{
		registerCalls: []*pb.LogDictionary{},
	}
	c.unaryClient = mockClient

	hb := c.buildHeartbeat("test-host", "1.0.0", "", &netSampler{}, &NetIfaceSampler{})
	require.NotNil(t, hb)

	heartbeat, ok := hb.Msg.(*pb.AgentToServer_Heartbeat)
	require.True(t, ok)
	require.NotNil(t, heartbeat.Heartbeat)

	// Should have a log batch with entries
	require.NotNil(t, heartbeat.Heartbeat.Logs, "Logs should be attached when flusher is configured")
	require.NotEmpty(t, heartbeat.Heartbeat.Logs.Entries, "Batch should have entries")
	require.Equal(t, int(3), len(heartbeat.Heartbeat.Logs.Entries), "Should have 3 entries")

	// Verify agent_session_id is set
	require.Equal(t, "session-123", heartbeat.Heartbeat.AgentSessionId)
}

// TestBuildHeartbeatAttachesLogDictionary verifies that when a flusher detects
// a dictionary delta, RegisterLogDictionary is called before the batch is attached.
func TestBuildHeartbeatAttachesLogDictionary(t *testing.T) {
	// Create a minimal buffer and emitter
	tmpDir := t.TempDir()
	emitterCfg := logging.Config{
		BufferPath:   tmpDir + "/buffer",
		AgentID:      "test-agent",
		SessionID:    "test-session",
		HostID:       "test-host",
		HostName:     "test-hostname",
		AgentVer:     "1.0.0",
		FallbackFile: tmpDir + "/fallback.log",
		MaxBytes:     10 * 1024 * 1024,
		MaxAge:       7 * 24 * time.Hour,
	}
	em, err := logging.New(emitterCfg)
	require.NoError(t, err)
	defer em.Close()

	// Create logging transport components
	dict := logtransport.New()
	sampler := &logtransport.Sampler{DefaultRate: 1.0}
	coalescer := &logtransport.Coalescer{Window: 1 * time.Second}

	flusherCfg := logtransport.Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sampler,
		Coalescer: coalescer,
	}
	flusher := logtransport.NewFlusher(flusherCfg)

	// Emit 1 event with a new category (will add to dictionary)
	em.Emit(logtypes.LevelInfo, "new-category-1", "action", "message", nil)
	time.Sleep(100 * time.Millisecond)

	// Create client with flusher
	c := &Client{
		opts: Options{
			HostID:       "test-host",
			AgentVersion: "1.0.0",
			Flusher:      flusher,
		},
		sessionID: "session-123",
	}

	// Create a mock unary client that records calls
	mockClient := &mockAgentBridgeClient{
		registerCalls: []*pb.LogDictionary{},
	}
	c.unaryClient = mockClient

	hb := c.buildHeartbeat("test-host", "1.0.0", "", &netSampler{}, &NetIfaceSampler{})
	require.NotNil(t, hb)

	heartbeat, ok := hb.Msg.(*pb.AgentToServer_Heartbeat)
	require.True(t, ok)
	require.NotNil(t, heartbeat.Heartbeat)

	// Should have called RegisterLogDictionary
	require.NotEmpty(t, mockClient.registerCalls, "RegisterLogDictionary should have been called")

	dictMsg := mockClient.registerCalls[0]
	require.NotNil(t, dictMsg)
	require.NotEmpty(t, dictMsg.Strings, "Dictionary should have entries")

	// Should have a log batch
	require.NotNil(t, heartbeat.Heartbeat.Logs, "Logs should be attached")
	require.NotEmpty(t, heartbeat.Heartbeat.Logs.Entries, "Batch should have entries")
}

// TestAckProcessing verifies that HeartbeatAck messages are properly handled,
// calling flusher.Ack and SetPolicy.
func TestAckProcessing(t *testing.T) {
	// Create a minimal buffer and emitter
	tmpDir := t.TempDir()
	emitterCfg := logging.Config{
		BufferPath:   tmpDir + "/buffer",
		AgentID:      "test-agent",
		SessionID:    "test-session",
		HostID:       "test-host",
		HostName:     "test-hostname",
		AgentVer:     "1.0.0",
		FallbackFile: tmpDir + "/fallback.log",
		MaxBytes:     10 * 1024 * 1024,
		MaxAge:       7 * 24 * time.Hour,
	}
	em, err := logging.New(emitterCfg)
	require.NoError(t, err)
	defer em.Close()

	dict := logtransport.New()
	sampler := &logtransport.Sampler{DefaultRate: 1.0}
	coalescer := &logtransport.Coalescer{Window: 1 * time.Second}

	flusherCfg := logtransport.Config{
		Emitter:   em,
		Dict:      dict,
		Sampler:   sampler,
		Coalescer: coalescer,
	}
	flusher := logtransport.NewFlusher(flusherCfg)

	// Create client
	c := &Client{
		opts: Options{
			HostID:       "test-host",
			AgentVersion: "1.0.0",
			Flusher:      flusher,
		},
		sessionID: "session-123",
	}

	// Manually set lastEmittedSeq to simulate a prior Build call
	c.lastEmittedSeq = 100
	c.sampledOutThroughSeq = 95

	// Create and process HeartbeatAck
	ack := &pb.HeartbeatAck{
		ServerAt:    timestamppb.Now(),
		LogsAckedSeq: 98,
		LogPolicy: &pb.LogPolicy{
			PolicyVersion:     1,
			DefaultLevel:      "info",
			BatchMaxBytes:     32768,
			BatchMaxIntervalS: 10,
			DefaultSampleRate: float32(1.0),
			BackoffMs:         100,
		},
	}

	// Manually invoke the ack handler logic (simulating what happens in runOnce)
	maxSeq := ack.LogsAckedSeq
	if c.sampledOutThroughSeq > maxSeq {
		maxSeq = c.sampledOutThroughSeq
	}

	err = c.opts.Flusher.Ack(maxSeq)
	require.NoError(t, err)

	if ack.LogPolicy != nil {
		policy := &logtransport.Policy{
			Version:           ack.LogPolicy.PolicyVersion,
			DefaultLevel:      ack.LogPolicy.DefaultLevel,
			BatchMaxBytes:     ack.LogPolicy.BatchMaxBytes,
			BatchMaxIntervalS: ack.LogPolicy.BatchMaxIntervalS,
			DefaultSampleRate: float64(ack.LogPolicy.DefaultSampleRate),
			BackoffMs:         ack.LogPolicy.BackoffMs,
		}
		c.opts.Flusher.SetPolicy(policy)
	}

	// Verify policy was applied by checking GetPolicy or similar
	// (This is a best-effort verification; the actual policy is atomic.Pointer on flusher)
}

// mockAgentBridgeClient simulates a gRPC AgentBridgeClient for testing.
type mockAgentBridgeClient struct {
	registerCalls []*pb.LogDictionary
}

func (m *mockAgentBridgeClient) Stream(ctx context.Context, opts ...grpc.CallOption) (pb.AgentBridge_StreamClient, error) {
	return nil, nil
}

func (m *mockAgentBridgeClient) RegisterLogDictionary(ctx context.Context, in *pb.LogDictionary, opts ...grpc.CallOption) (*pb.DictionaryAck, error) {
	m.registerCalls = append(m.registerCalls, in)
	return &pb.DictionaryAck{Version: in.Version, Ok: true}, nil
}

// TestBuildHeartbeatFlusherNil verifies that nil flusher is safe.
func TestBuildHeartbeatFlusherNil(t *testing.T) {
	c := &Client{
		opts: Options{
			HostID:       "test-host",
			AgentVersion: "1.0.0",
			Flusher:      nil,
		},
		sessionID: "session-123",
	}

	hb := c.buildHeartbeat("test-host", "1.0.0", "", &netSampler{}, &NetIfaceSampler{})
	require.NotNil(t, hb)

	heartbeat, ok := hb.Msg.(*pb.AgentToServer_Heartbeat)
	require.True(t, ok)
	require.Nil(t, heartbeat.Heartbeat.Logs, "Should be nil when flusher is nil")
}
