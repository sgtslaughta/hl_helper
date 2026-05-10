package enrollment

import (
	"context"
	"crypto/x509"
	"errors"
	"fmt"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type GRPCReenrollServer struct {
	Endpoint   string // e.g. "fleet.example.com:7444"
	RootCAPEM  []byte
}

func (g *GRPCReenrollServer) dial(ctx context.Context) (*grpc.ClientConn, error) {
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(g.RootCAPEM) {
		return nil, errors.New("invalid root CA pem")
	}
	creds := credentials.NewClientTLSFromCert(pool, "")
	return grpc.DialContext(
		ctx,
		g.Endpoint,
		grpc.WithTransportCredentials(creds),
		grpc.WithBlock(),
	)
}

func (g *GRPCReenrollServer) Challenge(ctx context.Context, hostID string, signingPubkey []byte) ([]byte, error) {
	dialCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	conn, err := g.dial(dialCtx)
	if err != nil {
		return nil, fmt.Errorf("dial: %w", err)
	}
	defer conn.Close()

	c := pb.NewReEnrollClient(conn)
	resp, err := c.Challenge(ctx, &pb.ChallengeRequest{
		HostId:        hostID,
		SigningPubkey: signingPubkey,
	})
	if err != nil {
		return nil, err
	}
	return resp.Nonce, nil
}

func (g *GRPCReenrollServer) Complete(ctx context.Context, hostID string, nonce, sig, csr []byte, tsUnix int64) ([]byte, error) {
	dialCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	conn, err := g.dial(dialCtx)
	if err != nil {
		return nil, fmt.Errorf("dial: %w", err)
	}
	defer conn.Close()

	c := pb.NewReEnrollClient(conn)
	resp, err := c.Complete(ctx, &pb.CompleteRequest{
		HostId:    hostID,
		Nonce:     nonce,
		Signature: sig,
		CsrPem:    csr,
		Ts:        timestamppb.New(time.Unix(tsUnix, 0).UTC()),
	})
	if err != nil {
		return nil, err
	}
	return resp.CertChainPem, nil
}
