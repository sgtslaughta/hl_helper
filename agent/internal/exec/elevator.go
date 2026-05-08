package exec

import (
	"errors"
	"os"
	osexec "os/exec"
)

// ErrNoElevator is returned when no privilege escalation path is available.
var ErrNoElevator = errors.New("exec: no elevator available (no sudo, no doas, not root)")

// ElevatorKind identifies which mechanism (if any) provides elevation.
type ElevatorKind string

const (
	ElevatorSudo   ElevatorKind = "sudo"
	ElevatorDoas   ElevatorKind = "doas"
	ElevatorDirect ElevatorKind = "direct" // already root, no wrapper
	ElevatorNone   ElevatorKind = "none"
)

// Elevator describes the resolved elevation strategy.
type Elevator struct {
	Kind ElevatorKind
	Path string // absolute path to wrapper binary; empty for direct/none
}

// DetectElevator probes the system. Order: sudo, doas, direct (euid==0), none.
func DetectElevator() Elevator {
	if p, err := osexec.LookPath("sudo"); err == nil {
		return Elevator{Kind: ElevatorSudo, Path: p}
	}
	if p, err := osexec.LookPath("doas"); err == nil {
		return Elevator{Kind: ElevatorDoas, Path: p}
	}
	if os.Geteuid() == 0 {
		return Elevator{Kind: ElevatorDirect}
	}
	return Elevator{Kind: ElevatorNone}
}

// Wrap returns (binary, args) suitable for exec.Command to run `bin args...`
// with elevated privileges. Returns ErrNoElevator if Kind == ElevatorNone.
func (e Elevator) Wrap(bin string, args []string) (string, []string, error) {
	switch e.Kind {
	case ElevatorSudo:
		out := append([]string{"--non-interactive", "--", bin}, args...)
		return e.Path, out, nil
	case ElevatorDoas:
		out := append([]string{"-n", "--", bin}, args...)
		return e.Path, out, nil
	case ElevatorDirect:
		return bin, args, nil
	default:
		return "", nil, ErrNoElevator
	}
}
