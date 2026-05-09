package rotator

import (
	"context"
	"fmt"
	"path/filepath"
	"testing"
	"time"
)

type fakeTransport struct {
	sentCSR  []byte
	sentPub  []byte
	sentPrev string
	issueCh  chan *CertIssue
	reconn   int
}

func (f *fakeTransport) SendCertRotate(_ context.Context, csr, pub []byte, prevSerial string) error {
	f.sentCSR = csr
	f.sentPub = pub
	f.sentPrev = prevSerial
	return nil
}
func (f *fakeTransport) AwaitCertIssue(ctx context.Context) (*CertIssue, error) {
	select {
	case m := <-f.issueCh:
		return m, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}
func (f *fakeTransport) Reconnect() { f.reconn++ }

type fakeKS struct {
	rotateCalls int
	staged      bool
	committed   bool
	verifyOK    bool
}

func (k *fakeKS) RotateTLS(cn string) ([]byte, []byte, []byte, error) {
	k.rotateCalls++
	return []byte("CSR"), []byte("PUB"), []byte("PRIV"), nil
}
func (k *fakeKS) StageTLS(chain, priv []byte) error    { k.staged = true; return nil }
func (k *fakeKS) VerifyStagedTLS() error               { return errIfFalse(k.verifyOK) }
func (k *fakeKS) CommitTLS() error                     { k.committed = true; return nil }
func (k *fakeKS) RollbackStagedTLS() error             { return nil }
func (k *fakeKS) SigningPub() []byte                   { return []byte("SIGNPUB") }

func errIfFalse(ok bool) error {
	if ok {
		return nil
	}
	return fmt.Errorf("verify failed")
}

func TestRotatorHappyPath(t *testing.T) {
	tp := &fakeTransport{issueCh: make(chan *CertIssue, 1)}
	tp.issueCh <- &CertIssue{CertChainPEM: []byte("CHAIN")}
	ks := &fakeKS{verifyOK: true}

	r := New(Config{
		HostID:       "h-1",
		Transport:    tp,
		Keystore:     ks,
		StatePath:    filepath.Join(t.TempDir(), "rotator.json"),
		PrevSerialFn: func() (string, error) { return "OLD", nil },
		MaxBackoff:   1 * time.Second,
	})
	if err := r.RotateOnce(context.Background()); err != nil {
		t.Fatalf("RotateOnce: %v", err)
	}
	if !ks.staged || !ks.committed {
		t.Errorf("expected staged + committed, got staged=%v committed=%v", ks.staged, ks.committed)
	}
	if tp.reconn != 1 {
		t.Errorf("Reconnect calls = %d, want 1", tp.reconn)
	}
}

func TestRotatorVerifyFailureRollsBack(t *testing.T) {
	tp := &fakeTransport{issueCh: make(chan *CertIssue, 1)}
	tp.issueCh <- &CertIssue{CertChainPEM: []byte("BADCHAIN")}
	ks := &fakeKS{verifyOK: false}

	r := New(Config{
		HostID:       "h-1",
		Transport:    tp,
		Keystore:     ks,
		StatePath:    filepath.Join(t.TempDir(), "rotator.json"),
		PrevSerialFn: func() (string, error) { return "OLD", nil },
	})
	err := r.RotateOnce(context.Background())
	if err == nil {
		t.Fatal("expected error on verify fail")
	}
	if ks.committed {
		t.Errorf("must not commit on verify fail")
	}
	if tp.reconn != 0 {
		t.Errorf("must not reconnect on verify fail, got %d", tp.reconn)
	}
}
