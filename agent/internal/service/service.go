package service

import "io"

type State string

const (
	StateRunning State = "running"
	StateStopped State = "stopped"
	StateUnknown State = "unknown"
	StateFailed  State = "failed"
)

// Unit describes the service to be installed.
type Unit struct {
	Name        string            // e.g. "hl-agent"
	Description string
	ExecPath    string            // absolute path to binary
	ExecArgs    []string          // args after binary, e.g. ["run", "--dir", "/var/lib/hl-agent"]
	User        string            // empty = root
	Environment map[string]string
}

type Manager interface {
	Kind() string                       // "systemd", "openrc", "launchd", "sysv"
	Install(u Unit) error               // writes unit file + enables
	Uninstall(name string) error        // disables + removes unit file
	Start(name string) error
	Stop(name string) error
	Restart(name string) error
	Status(name string) (State, error)
	Logs(name string, follow bool, lines int) (io.ReadCloser, error)
}
