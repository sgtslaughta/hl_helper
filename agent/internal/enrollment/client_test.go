package enrollment_test

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/hlhelper/hl-agent/internal/enrollment"
	"github.com/hlhelper/hl-agent/internal/keystore"
)

func TestRunHappyPath(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/v1/enroll" {
			t.Errorf("expected /v1/enroll, got %s", r.URL.Path)
		}

		var req map[string]interface{}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("failed to decode request: %v", err)
		}

		resp := enrollment.EnrollResponse{
			HostID:                "host-123",
			LeafCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			IntermediateCertPEM:   "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			RootCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			ServerSigningPubKeyB64: "dGVzdA==",
			GRPCEndpoint:          "127.0.0.1:50051",
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	resp, err := enrollment.Run(ks, enrollment.EnrollOptions{
		Server:   server.URL,
		Token:    "hlb_test",
		Hostname: "test-host",
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	if resp.HostID != "host-123" {
		t.Errorf("expected host_id=host-123, got %s", resp.HostID)
	}

	// Verify certs are persisted
	leafData, err := os.ReadFile(filepath.Join(tmpdir, "tls.crt"))
	if err != nil {
		t.Fatalf("failed to read leaf cert: %v", err)
	}
	if !bytes.Contains(leafData, []byte("BEGIN CERTIFICATE")) {
		t.Error("leaf cert not properly persisted")
	}

	// Verify manifest is written
	manifestPath := filepath.Join(tmpdir, "manifest.json")
	manifestData, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatalf("manifest not found: %v", err)
	}

	var manifest map[string]interface{}
	if err := json.Unmarshal(manifestData, &manifest); err != nil {
		t.Fatalf("failed to decode manifest: %v", err)
	}
	if manifest["host_id"] != "host-123" {
		t.Errorf("manifest missing or wrong host_id")
	}
	if manifest["grpc_endpoint"] != "127.0.0.1:50051" {
		t.Errorf("manifest missing or wrong grpc_endpoint")
	}
	if manifest["server_signing_pubkey_b64"] != "dGVzdA==" {
		t.Errorf("manifest missing or wrong server_signing_pubkey_b64")
	}
}

func TestRunReturnsErrorOnNon2xx(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusGone) // 410
	}))
	defer server.Close()

	_, err = enrollment.Run(ks, enrollment.EnrollOptions{
		Server:   server.URL,
		Token:    "hlb_test",
		Hostname: "test-host",
	})
	if err == nil {
		t.Fatal("expected error on 410 status")
	}
}

func TestRunIncludesAllRequiredFields(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	var capturedReq map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&capturedReq); err != nil {
			t.Fatalf("failed to decode request: %v", err)
		}

		resp := enrollment.EnrollResponse{
			HostID:                "host-123",
			LeafCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			IntermediateCertPEM:   "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			RootCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			ServerSigningPubKeyB64: "dGVzdA==",
			GRPCEndpoint:          "127.0.0.1:50051",
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	_, err = enrollment.Run(ks, enrollment.EnrollOptions{
		Server:   server.URL,
		Token:    "hlb_test",
		Hostname: "test-host",
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	// Verify request fields
	if _, ok := capturedReq["token"]; !ok {
		t.Error("request missing token field")
	}
	if _, ok := capturedReq["hostname"]; !ok {
		t.Error("request missing hostname field")
	}
	if _, ok := capturedReq["csr_pem"]; !ok {
		t.Error("request missing csr_pem field")
	}
	if _, ok := capturedReq["agent_pubkey_b64"]; !ok {
		t.Error("request missing agent_pubkey_b64 field")
	}

	// Verify CSR is valid
	if csrPEM, ok := capturedReq["csr_pem"].(string); ok {
		block, _ := pem.Decode([]byte(csrPEM))
		if block == nil {
			t.Error("csr_pem is not valid PEM")
		} else {
			csr, err := x509.ParseCertificateRequest(block.Bytes)
			if err != nil {
				t.Errorf("failed to parse CSR: %v", err)
			}
			if csr.Subject.CommonName != "test-host" {
				t.Errorf("CSR CN should be test-host, got %s", csr.Subject.CommonName)
			}
		}
	}
}

func TestRunGeneratesSigningKeyIfMissing(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	// Verify no signing key initially
	signingKeyPath := filepath.Join(tmpdir, "signing.key")
	if _, err := os.Stat(signingKeyPath); !os.IsNotExist(err) {
		t.Fatal("signing.key should not exist initially")
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := enrollment.EnrollResponse{
			HostID:                "host-123",
			LeafCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			IntermediateCertPEM:   "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			RootCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			ServerSigningPubKeyB64: "dGVzdA==",
			GRPCEndpoint:          "127.0.0.1:50051",
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	_, err = enrollment.Run(ks, enrollment.EnrollOptions{
		Server:   server.URL,
		Token:    "hlb_test",
		Hostname: "test-host",
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	// Verify signing key was generated
	if _, err := os.Stat(signingKeyPath); os.IsNotExist(err) {
		t.Fatal("signing.key should have been generated")
	}
}

func TestRunGeneratesTLSKeyIfMissing(t *testing.T) {
	tmpdir := t.TempDir()
	ks, err := keystore.OpenFile(tmpdir)
	if err != nil {
		t.Fatal(err)
	}

	// Verify no TLS key initially
	tlsKeyPath := filepath.Join(tmpdir, "tls.key")
	if _, err := os.Stat(tlsKeyPath); !os.IsNotExist(err) {
		t.Fatal("tls.key should not exist initially")
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := enrollment.EnrollResponse{
			HostID:                "host-123",
			LeafCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			IntermediateCertPEM:   "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			RootCertPEM:           "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
			ServerSigningPubKeyB64: "dGVzdA==",
			GRPCEndpoint:          "127.0.0.1:50051",
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	_, err = enrollment.Run(ks, enrollment.EnrollOptions{
		Server:   server.URL,
		Token:    "hlb_test",
		Hostname: "test-host",
	})
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}

	// Verify TLS key was generated
	if _, err := os.Stat(tlsKeyPath); os.IsNotExist(err) {
		t.Fatal("tls.key should have been generated")
	}

	// Verify TLS key is valid ECDSA P-256
	tlsKeyData, err := os.ReadFile(tlsKeyPath)
	if err != nil {
		t.Fatalf("failed to read tls.key: %v", err)
	}
	block, _ := pem.Decode(tlsKeyData)
	if block == nil {
		t.Fatal("tls.key is not valid PEM")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		t.Fatalf("failed to parse TLS key: %v", err)
	}
	ecdsaKey, ok := key.(*ecdsa.PrivateKey)
	if !ok {
		t.Fatal("TLS key is not ECDSA")
	}
	if ecdsaKey.PublicKey.Curve.Params().Name != "P-256" {
		t.Fatalf("expected P-256 curve, got %s", ecdsaKey.PublicKey.Curve.Params().Name)
	}
}
