// Package manifest persists the agent's capability manifest negotiated at enrollment.
package manifest

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// Manifest holds the agent's authorized actions, risk threshold, and server pubkey.
type Manifest struct {
	HostID                string   `json:"host_id"`
	GRPCEndpoint          string   `json:"grpc_endpoint"`
	ServerSigningPubKeyB64 string  `json:"server_signing_pubkey_b64"`
	AllowedActions        []string `json:"allowed_actions"`
	MaxRisk               string   `json:"max_risk"`
}

// DefaultManifest returns a manifest with default safe values.
func DefaultManifest() Manifest {
	return Manifest{
		AllowedActions: []string{
			"pkg.update",
			"reboot",
			"shell.exec",
			"get_facts",
			"docker.op",
			"plugin.invoke",
			"terminal.open",
			"file.transfer",
		},
		MaxRisk: "high",
	}
}

// Load reads and parses manifest.json from the given directory.
func Load(dir string) (*Manifest, error) {
	path := filepath.Join(dir, "manifest.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var m Manifest
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, err
	}

	return &m, nil
}

// Save writes the manifest to manifest.json in the given directory.
func (m *Manifest) Save(dir string) error {
	data, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return err
	}

	path := filepath.Join(dir, "manifest.json")
	return os.WriteFile(path, data, 0o600)
}

// AllowsAction returns true if the action is in the allowed list.
func (m *Manifest) AllowsAction(action string) bool {
	for _, a := range m.AllowedActions {
		if a == action {
			return true
		}
	}
	return false
}

// AllowsRisk returns true if the risk level is at or below the manifest's max risk.
// Risk ordering: low < medium < high < critical.
func (m *Manifest) AllowsRisk(risk string) bool {
	return RiskLevel(risk) <= RiskLevel(m.MaxRisk)
}

// RiskLevel converts a risk string to an int for comparison.
// Returns: low=0, medium=1, high=2, critical=3.
func RiskLevel(s string) int {
	switch s {
	case "low":
		return 0
	case "medium":
		return 1
	case "high":
		return 2
	case "critical":
		return 3
	default:
		return -1 // unknown
	}
}
