//go:build unix

package updater

import "syscall"

// SyscallRelaunch replaces the current process image with argv0.
// PID is preserved (systemd / launchd watchdog stays attached).
var SyscallRelaunch RelaunchFn = syscall.Exec
