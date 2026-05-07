package updater

import (
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"fmt"
)

type Manifest struct {
	Version        string `json:"version"`
	Channel        string `json:"channel"`
	OS             string `json:"os"`
	Arch           string `json:"arch"`
	SHA256         string `json:"sha256"`
	Size           int64  `json:"size"`
	ReleasedAt     string `json:"released_at"`
	MinPrevVersion string `json:"min_prev_version"`
}

var ErrSigInvalid = errors.New("manifest signature invalid")

func VerifyManifest(body, sig []byte, pub ed25519.PublicKey) (Manifest, error) {
	var m Manifest
	if !ed25519.Verify(pub, body, sig) {
		return m, ErrSigInvalid
	}
	if err := json.Unmarshal(body, &m); err != nil {
		return m, fmt.Errorf("manifest decode: %w", err)
	}
	return m, nil
}
