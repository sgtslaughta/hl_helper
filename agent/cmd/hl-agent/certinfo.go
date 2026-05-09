package main

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"time"

	"github.com/hlhelper/hl-agent/internal/keystore"
)

func certInfoFromKeystore(ks keystore.Keystore) func() (time.Time, time.Time, string, error) {
	return func() (time.Time, time.Time, string, error) {
		chainPEM, _, err := ks.TLSCertAndKey()
		if err != nil {
			return time.Time{}, time.Time{}, "", err
		}
		block, _ := pem.Decode(chainPEM)
		if block == nil {
			return time.Time{}, time.Time{}, "", fmt.Errorf("no leaf cert in chain")
		}
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return time.Time{}, time.Time{}, "", err
		}
		return cert.NotBefore, cert.NotAfter, fmt.Sprintf("%x", cert.SerialNumber), nil
	}
}
