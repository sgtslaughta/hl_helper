package hostinfo

import "time"

type HostInfo struct {
	HostID       string    `json:"host_id"`
	GrpcEndpoint string    `json:"grpc_endpoint"`
	AgentVersion string    `json:"agent_version"`
	Hostname     string    `json:"hostname"`
	OS           string    `json:"os"`
	OSVersion    string    `json:"os_version"`
	Arch         string    `json:"arch"`
	StateDir     string    `json:"state_dir"`
	BinaryPath   string    `json:"binary_path"`
	CertNotAfter time.Time `json:"cert_not_after,omitempty"`
	Sleeping     bool      `json:"sleeping"`
	SleepUntil   time.Time `json:"sleep_until,omitempty"`

	// Live connection state derived from <stateDir>/heartbeat.json.
	HeartbeatAt    time.Time `json:"heartbeat_at,omitempty"`
	HeartbeatOK    bool      `json:"heartbeat_ok"`
	HeartbeatError string    `json:"heartbeat_error,omitempty"`
	StateDirError  string    `json:"state_dir_error,omitempty"`
}
