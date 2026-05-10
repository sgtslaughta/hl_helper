package rotator

import (
	"context"
	"testing"

	"github.com/hlhelper/hl-agent/internal/logging"
)

// MockTransport is a stub for testing.
type MockTransport struct {
	SendCertRotateFn func(ctx context.Context, csrPEM, signingPubkey []byte, prevSerial string) error
	AwaitCertIssueFn func(ctx context.Context) (*CertIssue, error)
}

func (m *MockTransport) SendCertRotate(ctx context.Context, csrPEM, signingPubkey []byte, prevSerial string) error {
	if m.SendCertRotateFn != nil {
		return m.SendCertRotateFn(ctx, csrPEM, signingPubkey, prevSerial)
	}
	return nil
}

func (m *MockTransport) AwaitCertIssue(ctx context.Context) (*CertIssue, error) {
	if m.AwaitCertIssueFn != nil {
		return m.AwaitCertIssueFn(ctx)
	}
	return nil, nil
}

func (m *MockTransport) Reconnect() {}

// MockKeystore is a stub for testing.
type MockKeystore struct {
	RotateTLSFn      func(commonName string) (csrPEM, pubDER, privPEM []byte, err error)
	StageTLSFn       func(chainPEM, privPEM []byte) error
	VerifyStagedTLSFn func() error
	CommitTLSFn      func() error
	SigningPubFn     func() []byte
}

func (m *MockKeystore) RotateTLS(commonName string) (csrPEM, pubDER, privPEM []byte, err error) {
	if m.RotateTLSFn != nil {
		return m.RotateTLSFn(commonName)
	}
	return []byte{}, []byte{}, []byte{}, nil
}

func (m *MockKeystore) StageTLS(chainPEM, privPEM []byte) error {
	if m.StageTLSFn != nil {
		return m.StageTLSFn(chainPEM, privPEM)
	}
	return nil
}

func (m *MockKeystore) VerifyStagedTLS() error {
	if m.VerifyStagedTLSFn != nil {
		return m.VerifyStagedTLSFn()
	}
	return nil
}

func (m *MockKeystore) CommitTLS() error {
	if m.CommitTLSFn != nil {
		return m.CommitTLSFn()
	}
	return nil
}

func (m *MockKeystore) RollbackStagedTLS() error {
	return nil
}

func (m *MockKeystore) SigningPub() []byte {
	if m.SigningPubFn != nil {
		return m.SigningPubFn()
	}
	return []byte{}
}

func TestRotateOnceEmitsSuccess(t *testing.T) {
	fake := &logging.FakeEmitter{}
	mockKS := &MockKeystore{
		RotateTLSFn: func(commonName string) ([]byte, []byte, []byte, error) {
			return []byte("csr"), []byte("pub"), []byte("priv"), nil
		},
		StageTLSFn: func(chainPEM, privPEM []byte) error {
			return nil
		},
		VerifyStagedTLSFn: func() error {
			return nil
		},
		CommitTLSFn: func() error {
			return nil
		},
		SigningPubFn: func() []byte {
			return []byte("signing-pub")
		},
	}
	mockTransport := &MockTransport{
		SendCertRotateFn: func(ctx context.Context, csrPEM, signingPubkey []byte, prevSerial string) error {
			return nil
		},
		AwaitCertIssueFn: func(ctx context.Context) (*CertIssue, error) {
			return &CertIssue{CertChainPEM: []byte("chain")}, nil
		},
	}
	r := New(Config{
		HostID:    "host1",
		Transport: mockTransport,
		Keystore:  mockKS,
		StatePath: t.TempDir() + "/state.json",
		PrevSerialFn: func() (string, error) {
			return "prev-serial-123", nil
		},
		Emitter: fake,
	})
	err := r.RotateOnce(context.Background())
	if err != nil {
		t.Fatalf("RotateOnce failed: %v", err)
	}
	if len(fake.Events) == 0 {
		t.Fatal("expected at least 1 event")
	}
	ev := fake.Events[0]
	if ev.Action != "cert.rotate.completed" {
		t.Fatalf("want action=cert.rotate.completed, got %s", ev.Action)
	}
	if ev.Category != "cert" {
		t.Fatalf("want category=cert, got %s", ev.Category)
	}
}

func TestRotateOnceWithNilEmitter(t *testing.T) {
	mockKS := &MockKeystore{
		RotateTLSFn: func(commonName string) ([]byte, []byte, []byte, error) {
			return []byte("csr"), []byte("pub"), []byte("priv"), nil
		},
		StageTLSFn: func(chainPEM, privPEM []byte) error {
			return nil
		},
		VerifyStagedTLSFn: func() error {
			return nil
		},
		CommitTLSFn: func() error {
			return nil
		},
		SigningPubFn: func() []byte {
			return []byte("signing-pub")
		},
	}
	mockTransport := &MockTransport{
		SendCertRotateFn: func(ctx context.Context, csrPEM, signingPubkey []byte, prevSerial string) error {
			return nil
		},
		AwaitCertIssueFn: func(ctx context.Context) (*CertIssue, error) {
			return &CertIssue{CertChainPEM: []byte("chain")}, nil
		},
	}
	r := New(Config{
		HostID:    "host1",
		Transport: mockTransport,
		Keystore:  mockKS,
		StatePath: t.TempDir() + "/state.json",
		PrevSerialFn: func() (string, error) {
			return "prev-serial-123", nil
		},
		Emitter: nil,
	})
	// Should not panic
	_ = r.RotateOnce(context.Background())
}
