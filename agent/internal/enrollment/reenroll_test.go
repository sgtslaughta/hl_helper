package enrollment

import (
	"context"
	"crypto/ed25519"
	"fmt"
	"testing"
)

type fakeReenrollServer struct {
	hostID     string
	pubkey     ed25519.PublicKey
	nonce      []byte
	signedOK   bool
	chainPEM   []byte
	csrSeen    []byte
	challenges int
	completes  int
}

func (f *fakeReenrollServer) Challenge(_ context.Context, hostID string, pubkey []byte) ([]byte, error) {
	f.challenges++
	f.hostID = hostID
	f.pubkey = pubkey
	return f.nonce, nil
}

func (f *fakeReenrollServer) Complete(_ context.Context, hostID string, nonce, sig, csr []byte, ts int64) ([]byte, error) {
	f.completes++
	if hostID == f.hostID && bytesEqual(nonce, f.nonce) && ed25519.Verify(f.pubkey, CanonicalReenrollPayload(hostID, nonce, ts), sig) {
		f.signedOK = true
		f.csrSeen = csr
		return f.chainPEM, nil
	}
	return nil, fmt.Errorf("verify fail")
}

type fakeKeystoreSig struct {
	priv ed25519.PrivateKey
	pub  ed25519.PublicKey
}

func (k *fakeKeystoreSig) SigningPub() ed25519.PublicKey                 { return k.pub }
func (k *fakeKeystoreSig) Sign(msg []byte) ([]byte, error)               { return ed25519.Sign(k.priv, msg), nil }
func (k *fakeKeystoreSig) RotateTLS(cn string) ([]byte, []byte, []byte, error) {
	return []byte("CSR"), []byte("PUB"), []byte("PRIV"), nil
}
func (k *fakeKeystoreSig) StageTLS(c, p []byte) error { return nil }
func (k *fakeKeystoreSig) VerifyStagedTLS() error     { return nil }
func (k *fakeKeystoreSig) CommitTLS() error           { return nil }
func (k *fakeKeystoreSig) RollbackStagedTLS() error   { return nil }

func TestReenrollClientHappyPath(t *testing.T) {
	pub, priv, _ := ed25519.GenerateKey(nil)
	srv := &fakeReenrollServer{
		nonce:    []byte("\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77"),
		chainPEM: []byte("CHAIN"),
	}
	ks := &fakeKeystoreSig{priv: priv, pub: pub}
	c := &ReenrollClient{
		HostID:   "h-1",
		Keystore: ks,
		Server:   srv,
	}
	if err := c.Run(context.Background()); err != nil {
		t.Fatalf("Run: %v", err)
	}
	if srv.challenges != 1 || srv.completes != 1 {
		t.Errorf("calls: ch=%d co=%d", srv.challenges, srv.completes)
	}
	if !srv.signedOK {
		t.Errorf("signature verify failed server-side")
	}
}
