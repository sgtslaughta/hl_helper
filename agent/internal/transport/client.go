// Package transport runs the persistent agent -> server gRPC bidi stream.
package transport

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"log"
	"math/rand"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"

	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/outbox"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type Options struct {
	Endpoint    string
	Keystore    keystore.Keystore
	Outbox      *outbox.Outbox
	OnCommand   func(*pb.CommandEnvelope)
	BaseBackoff time.Duration
	MaxBackoff  time.Duration
	DialOptions []grpc.DialOption // override (tests use bufconn)
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

	recvErr := make(chan error, 1)
	go func() {
		for {
			msg, e := stream.Recv()
			if e != nil {
				recvErr <- e
				return
			}
			if cmd := msg.GetCommand(); cmd != nil && c.opts.OnCommand != nil {
				c.opts.OnCommand(cmd)
			}
		}
	}()

	return <-recvErr
}

func (c *Client) tlsCreds() (credentials.TransportCredentials, error) {
	chain, key, err := c.opts.Keystore.TLSCertAndKey()
	if err != nil {
		return nil, err
	}
	if len(chain) == 0 || len(key) == 0 {
		return nil, fmt.Errorf("transport: keystore has no TLS material — enroll first")
	}
	cert, err := tls.X509KeyPair(chain, key)
	if err != nil {
		return nil, err
	}
	rootPEM, err := c.opts.Keystore.RootCAPEM()
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if rootPEM != nil {
		pool.AppendCertsFromPEM(rootPEM)
	}
	cfg := &tls.Config{
		Certificates: []tls.Certificate{cert},
		RootCAs:      pool,
		MinVersion:   tls.VersionTLS13,
	}
	return credentials.NewTLS(cfg), nil
}
