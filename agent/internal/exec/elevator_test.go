package exec_test

import (
	"testing"

	xexec "github.com/hlhelper/hl-agent/internal/exec"
)

func TestDetectElevator_PrefersSudoWhenPresent(t *testing.T) {
	t.Setenv("PATH", "/usr/bin:/bin") // depends on host having sudo at /usr/bin/sudo
	e := xexec.DetectElevator()
	if e.Kind != xexec.ElevatorSudo && e.Kind != xexec.ElevatorDoas && e.Kind != xexec.ElevatorDirect && e.Kind != xexec.ElevatorNone {
		t.Fatalf("unexpected kind %q", e.Kind)
	}
}

func TestElevatorWrap_Sudo(t *testing.T) {
	e := xexec.Elevator{Kind: xexec.ElevatorSudo, Path: "/usr/bin/sudo"}
	bin, args, err := e.Wrap("/bin/ls", []string{"-la"})
	if err != nil {
		t.Fatal(err)
	}
	if bin != "/usr/bin/sudo" {
		t.Fatalf("bin=%q", bin)
	}
	want := []string{"--non-interactive", "--", "/bin/ls", "-la"}
	if len(args) != len(want) {
		t.Fatalf("args=%v want=%v", args, want)
	}
	for i := range want {
		if args[i] != want[i] {
			t.Fatalf("args[%d]=%q want=%q", i, args[i], want[i])
		}
	}
}

func TestElevatorWrap_Doas(t *testing.T) {
	e := xexec.Elevator{Kind: xexec.ElevatorDoas, Path: "/usr/bin/doas"}
	bin, args, err := e.Wrap("/bin/ls", []string{"-la"})
	if err != nil {
		t.Fatal(err)
	}
	if bin != "/usr/bin/doas" {
		t.Fatalf("bin=%q", bin)
	}
	want := []string{"-n", "--", "/bin/ls", "-la"}
	if len(args) != len(want) {
		t.Fatalf("args=%v want=%v", args, want)
	}
	for i := range want {
		if args[i] != want[i] {
			t.Fatalf("args[%d]=%q want=%q", i, args[i], want[i])
		}
	}
}

func TestElevatorWrap_Direct(t *testing.T) {
	e := xexec.Elevator{Kind: xexec.ElevatorDirect}
	bin, args, err := e.Wrap("/bin/ls", []string{"-la"})
	if err != nil {
		t.Fatal(err)
	}
	if bin != "/bin/ls" || len(args) != 1 || args[0] != "-la" {
		t.Fatalf("bin=%q args=%v", bin, args)
	}
}

func TestElevatorWrap_NoneReturnsErr(t *testing.T) {
	e := xexec.Elevator{Kind: xexec.ElevatorNone}
	if _, _, err := e.Wrap("/bin/ls", nil); err != xexec.ErrNoElevator {
		t.Fatalf("err=%v", err)
	}
}
