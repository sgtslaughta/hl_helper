package transport_test

import (
	"context"
	"errors"
	"net"
	"sync/atomic"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"

	"github.com/hlhelper/hl-agent/internal/transport"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type stubServer struct {
	pb.UnimplementedAgentBridgeServer
	onConnect func(stream grpc.BidiStreamingServer[pb.AgentToServer, pb.ServerToAgent]) error
}

func (s *stubServer) Stream(stream grpc.BidiStreamingServer[pb.AgentToServer, pb.ServerToAgent]) error {
	if s.onConnect != nil {
		return s.onConnect(stream)
	}
	return nil
}

func newBufServer(t *testing.T, srv pb.AgentBridgeServer) (*grpc.Server, *bufconn.Listener) {
	lis := bufconn.Listen(1024 * 1024)
	s := grpc.NewServer()
	pb.RegisterAgentBridgeServer(s, srv)
	go func() { _ = s.Serve(lis) }()
	t.Cleanup(s.Stop)
	return s, lis
}

func bufDialOpts(lis *bufconn.Listener) []grpc.DialOption {
	return []grpc.DialOption{
		grpc.WithContextDialer(func(_ context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(context.Background())
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	}
}

// TestRunOnceDeliversCommand tests that a command from server is delivered.
func TestRunOnceDeliversCommand(t *testing.T) {
	cmdReceived := make(chan *pb.CommandEnvelope, 1)

	srv := &stubServer{
		onConnect: func(stream grpc.BidiStreamingServer[pb.AgentToServer, pb.ServerToAgent]) error {
			msg := &pb.ServerToAgent{
				Msg: &pb.ServerToAgent_Command{
					Command: &pb.CommandEnvelope{
						CommandId: "test-cmd-1",
						HostId:    "host-1",
					},
				},
			}
			return stream.Send(msg)
		},
	}

	_, lis := newBufServer(t, srv)

	cli := transport.New(transport.Options{
		Endpoint: "localhost:9999",
		OnCommand: func(env *pb.CommandEnvelope) {
			cmdReceived <- env
		},
		DialOptions: bufDialOpts(lis),
	})

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_ = cli.RunOnce(ctx)

	select {
	case cmd := <-cmdReceived:
		if cmd.CommandId != "test-cmd-1" {
			t.Errorf("Expected CommandId test-cmd-1, got %s", cmd.CommandId)
		}
	case <-time.After(1 * time.Second):
		t.Errorf("OnCommand was not called within timeout")
	}
}

// TestRunReconnectsAfterError tests that Run retries after an error.
func TestRunReconnectsAfterError(t *testing.T) {
	connectCount := atomic.Int32{}

	srv := &stubServer{
		onConnect: func(stream grpc.BidiStreamingServer[pb.AgentToServer, pb.ServerToAgent]) error {
			connectCount.Add(1)
			if connectCount.Load() == 1 {
				return errors.New("simulated error")
			}
			// Second connection: hold open, then close
			<-time.After(100 * time.Millisecond)
			return errors.New("connection closed")
		},
	}

	_, lis := newBufServer(t, srv)

	cli := transport.New(transport.Options{
		Endpoint:    "localhost:9999",
		BaseBackoff: 10 * time.Millisecond,
		MaxBackoff:  30 * time.Millisecond,
		DialOptions: bufDialOpts(lis),
	})

	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	_ = cli.Run(ctx)

	// Should have reconnected at least once
	if connectCount.Load() < 2 {
		t.Errorf("Expected at least 2 connection attempts, got %d", connectCount.Load())
	}
}

// TestRunRespectsContextCancel tests that Run returns when context is canceled.
func TestRunRespectsContextCancel(t *testing.T) {
	srv := &stubServer{
		onConnect: func(stream grpc.BidiStreamingServer[pb.AgentToServer, pb.ServerToAgent]) error {
			// Hold the stream open
			<-time.After(5 * time.Second)
			return nil
		},
	}

	_, lis := newBufServer(t, srv)

	cli := transport.New(transport.Options{
		Endpoint:    "localhost:9999",
		DialOptions: bufDialOpts(lis),
	})

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		<-time.After(100 * time.Millisecond)
		cancel()
	}()

	err := cli.Run(ctx)
	if !errors.Is(err, context.Canceled) {
		t.Errorf("Expected context.Canceled, got %v", err)
	}
}
