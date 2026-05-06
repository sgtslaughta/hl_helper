// Package enrollment performs the agent's first-contact handshake with the server.
package enrollment

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"github.com/hlhelper/hl-agent/internal/keystore"
)

type EnrollResponse struct {
	HostID                string `json:"host_id"`
	LeafCertPEM           string `json:"leaf_cert_pem"`
	IntermediateCertPEM   string `json:"intermediate_cert_pem"`
	RootCertPEM           string `json:"root_cert_pem"`
	ServerSigningPubKeyB64 string `json:"server_signing_pubkey_b64"`
	GRPCEndpoint          string `json:"grpc_endpoint"`
}

type enrollRequest struct {
	Token            string `json:"token"`
	Hostname         string `json:"hostname"`
	CSRPEM           string `json:"csr_pem"`
	AgentPubKeyB64   string `json:"agent_pubkey_b64"`
}

type EnrollOptions struct {
	Server     string       // https://server:8443
	Token      string       // hlb_<base32>
	Hostname   string
	HTTPClient *http.Client // optional; nil = default with system roots
}

// Run performs:
// 1. ks.GenerateSigning() if needed.
// 2. ks.GenerateTLS() if needed (ECDSA P-256).
// 3. Build a CSR from the TLS keypair (CN=Hostname).
// 4. POST /v1/enroll with token + CSR PEM + agent_pubkey_b64 + hostname.
// 5. Persist response cert bundle into keystore (StoreEnrollmentBundle).
// 6. Persist host_id + grpc_endpoint + server_signing_pubkey to a manifest file under ks.Dir().
// 7. Return parsed EnrollResponse.
func Run(ks *keystore.FileKeystore, opts EnrollOptions) (*EnrollResponse, error) {
	// Step 1: Generate signing key if needed
	if err := ks.GenerateSigning(); err != nil {
		return nil, fmt.Errorf("generate signing key: %w", err)
	}

	// Step 2: Generate TLS key if needed
	if err := ks.GenerateTLS(); err != nil {
		return nil, fmt.Errorf("generate TLS key: %w", err)
	}

	// Step 3: Build CSR
	tlsKeyData, err := os.ReadFile(filepath.Join(ks.Dir(), keystore.TLSKeyFile))
	if err != nil {
		return nil, fmt.Errorf("read TLS key: %w", err)
	}
	block, _ := pem.Decode(tlsKeyData)
	if block == nil {
		return nil, fmt.Errorf("TLS key: invalid PEM")
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parse TLS key: %w", err)
	}
	tlsPrivKey, ok := parsed.(*ecdsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("TLS key is not ECDSA")
	}

	csrTemplate := &x509.CertificateRequest{
		Subject: pkix.Name{
			CommonName: opts.Hostname,
		},
	}
	csrDER, err := x509.CreateCertificateRequest(rand.Reader, csrTemplate, tlsPrivKey)
	if err != nil {
		return nil, fmt.Errorf("create CSR: %w", err)
	}
	csrPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE REQUEST", Bytes: csrDER})

	// Step 4: Build request
	// Server expects the raw 32-byte Ed25519 public key, base64-encoded
	// (see server/app/api/v1/enroll.py: len(agent_pubkey) != 32 → 400).
	signingPub := ks.SigningPub()
	if len(signingPub) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("unexpected signing pubkey size: %d", len(signingPub))
	}
	agentPubKeyB64 := base64.StdEncoding.EncodeToString(signingPub)

	req := enrollRequest{
		Token:          opts.Token,
		Hostname:       opts.Hostname,
		CSRPEM:         string(csrPEM),
		AgentPubKeyB64: agentPubKeyB64,
	}
	reqBody, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	// POST /v1/enroll
	httpClient := opts.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{}
	}

	httpResp, err := httpClient.Post(opts.Server+"/v1/enroll", "application/json", bytes.NewReader(reqBody))
	if err != nil {
		return nil, fmt.Errorf("post /v1/enroll: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode < 200 || httpResp.StatusCode >= 300 {
		body, _ := io.ReadAll(httpResp.Body)
		return nil, fmt.Errorf("enroll: server returned %d: %s", httpResp.StatusCode, string(body))
	}

	// Step 5: Parse response
	var resp EnrollResponse
	if err := json.NewDecoder(httpResp.Body).Decode(&resp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	// Step 6: Persist cert bundle
	if err := ks.StoreEnrollmentBundle([]byte(resp.LeafCertPEM), []byte(resp.IntermediateCertPEM), []byte(resp.RootCertPEM)); err != nil {
		return nil, fmt.Errorf("store enrollment bundle: %w", err)
	}

	// Step 7: Write manifest
	manifest := map[string]string{
		"host_id":                    resp.HostID,
		"grpc_endpoint":              resp.GRPCEndpoint,
		"server_signing_pubkey_b64":  resp.ServerSigningPubKeyB64,
	}
	manifestData, err := json.MarshalIndent(manifest, "", "")
	if err != nil {
		return nil, fmt.Errorf("marshal manifest: %w", err)
	}
	manifestPath := filepath.Join(ks.Dir(), "manifest.json")
	if err := os.WriteFile(manifestPath, manifestData, 0644); err != nil {
		return nil, fmt.Errorf("write manifest: %w", err)
	}

	return &resp, nil
}
