package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/manifest"
)

type checkResult struct {
	name  string
	pass  bool
	msg   string
	warn  bool // true = warning, false = error
}

func checkManifest(dir string) checkResult {
	m, err := manifest.Load(dir)
	if err != nil {
		return checkResult{
			name: "manifest",
			pass: false,
			msg:  fmt.Sprintf("load failed: %v", err),
		}
	}

	if m.HostID == "" {
		return checkResult{
			name: "manifest",
			pass: false,
			msg:  "host_id missing",
		}
	}

	return checkResult{
		name: "manifest",
		pass: true,
		msg:  fmt.Sprintf("host_id=%s", m.HostID),
	}
}

func checkKeystore(dir string) checkResult {
	_, err := keystore.OpenFile(dir)
	if err != nil {
		return checkResult{
			name: "keystore",
			pass: false,
			msg:  fmt.Sprintf("open failed: %v", err),
		}
	}

	return checkResult{
		name: "keystore",
		pass: true,
		msg:  "readable",
	}
}

func checkCert(dir string) checkResult {
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		return checkResult{
			name: "certificate",
			pass: false,
			msg:  fmt.Sprintf("keystore open failed: %v", err),
		}
	}

	// Get TLS certificate and parse it.
	certPEM, _, err := ks.TLSCertAndKey()
	if err != nil || len(certPEM) == 0 {
		return checkResult{
			name: "certificate",
			pass: false,
			msg:  "no certificate found",
		}
	}

	// Parse PEM to get NotAfter.
	block, _ := pem.Decode(certPEM)
	if block == nil {
		return checkResult{
			name: "certificate",
			pass: false,
			msg:  "cannot decode certificate PEM",
		}
	}

	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return checkResult{
			name: "certificate",
			pass: false,
			msg:  fmt.Sprintf("parse certificate: %v", err),
		}
	}

	notAfter := cert.NotAfter
	now := time.Now()
	expiresIn := notAfter.Sub(now)

	if expiresIn < 0 {
		return checkResult{
			name: "certificate",
			pass: false,
			msg:  "certificate expired",
		}
	}

	if expiresIn < 7*24*time.Hour {
		return checkResult{
			name: "certificate",
			pass: true,
			msg:  fmt.Sprintf("expires in %.1f days (warning)", expiresIn.Hours()/24),
			warn: true,
		}
	}

	return checkResult{
		name: "certificate",
		pass: true,
		msg:  fmt.Sprintf("expires in %.1f days", expiresIn.Hours()/24),
	}
}

func checkServerReach(dir string) checkResult {
	m, err := manifest.Load(dir)
	if err != nil {
		return checkResult{
			name: "server_reachability",
			pass: false,
			msg:  fmt.Sprintf("manifest load failed: %v", err),
		}
	}

	endpoint := m.GRPCEndpoint
	if endpoint == "" {
		return checkResult{
			name: "server_reachability",
			pass: false,
			msg:  "no endpoint in manifest",
		}
	}

	// Try TLS dial with 5s timeout.
	tlsConfig := &tls.Config{
		InsecureSkipVerify: true, // Reachability-only check
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	d := &tls.Dialer{
		Config: tlsConfig,
	}

	conn, err := d.DialContext(ctx, "tcp", endpoint)
	if err != nil {
		return checkResult{
			name: "server_reachability",
			pass: false,
			msg:  fmt.Sprintf("cannot reach %s: %v", endpoint, err),
		}
	}
	conn.Close()

	return checkResult{
		name: "server_reachability",
		pass: true,
		msg:  fmt.Sprintf("reachable at %s", endpoint),
	}
}

func checkClockSkew(dir string) checkResult {
	m, err := manifest.Load(dir)
	if err != nil {
		return checkResult{
			name: "clock_skew",
			pass: false,
			msg:  fmt.Sprintf("manifest load failed: %v", err),
		}
	}

	endpoint := m.GRPCEndpoint
	if endpoint == "" {
		return checkResult{
			name: "clock_skew",
			pass: true,
			msg:  "skipped (no endpoint)",
		}
	}

	// Extract host from endpoint (remove :port if present).
	host := endpoint
	if idx := strings.LastIndex(host, ":"); idx > 0 {
		host = host[:idx]
	}

	// Try HEAD request to /healthz.
	url := fmt.Sprintf("https://%s/healthz", host)
	client := &http.Client{
		Timeout: 5 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				InsecureSkipVerify: true,
			},
		},
	}

	resp, err := client.Head(url)
	if err != nil {
		return checkResult{
			name: "clock_skew",
			pass: true,
			msg:  "skipped (cannot reach /healthz)",
		}
	}
	defer resp.Body.Close()

	// Compare Date header with local clock.
	dateStr := resp.Header.Get("Date")
	if dateStr == "" {
		return checkResult{
			name: "clock_skew",
			pass: true,
			msg:  "skipped (no Date header)",
		}
	}

	serverTime, err := time.Parse(time.RFC1123, dateStr)
	if err != nil {
		return checkResult{
			name: "clock_skew",
			pass: true,
			msg:  "skipped (cannot parse Date)",
		}
	}

	drift := time.Now().Sub(serverTime)
	if drift < 0 {
		drift = -drift
	}

	if drift > 60*time.Second {
		return checkResult{
			name: "clock_skew",
			pass: true,
			msg:  fmt.Sprintf("drift %.0f seconds (warning)", drift.Seconds()),
			warn: true,
		}
	}

	return checkResult{
		name: "clock_skew",
		pass: true,
		msg:  fmt.Sprintf("drift %.0f seconds", drift.Seconds()),
	}
}

func checkStateDir(dir string) checkResult {
	// Test write temp file.
	testFile := filepath.Join(dir, ".doctor_test")
	if err := os.WriteFile(testFile, []byte("test"), 0o600); err != nil {
		return checkResult{
			name: "state_dir",
			pass: false,
			msg:  fmt.Sprintf("not writable: %v", err),
		}
	}

	_ = os.Remove(testFile)
	return checkResult{
		name: "state_dir",
		pass: true,
		msg:  "writable",
	}
}
