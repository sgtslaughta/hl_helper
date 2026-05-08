package service

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"runtime"
)

// Detect returns a Manager for the running OS. Order:
//   linux: systemd (if /run/systemd/system exists) → openrc (/sbin/openrc exists) → sysv (/etc/init.d + 'service' binary) → error
//   darwin: launchd
// Allow override via HL_INIT_SYSTEM env var (values: "systemd","openrc","launchd","sysv").
func Detect() (Manager, error) {
	// Check for override env var
	if override := os.Getenv("HL_INIT_SYSTEM"); override != "" {
		switch override {
		case "systemd":
			return newSystemd(), nil
		case "openrc":
			return newOpenRC(), nil
		case "launchd":
			return newLaunchd(), nil
		case "sysv":
			return newSysV(), nil
		default:
			return nil, fmt.Errorf("unknown HL_INIT_SYSTEM value: %s", override)
		}
	}

	// Auto-detect based on OS
	switch runtime.GOOS {
	case "linux":
		return detectLinux()
	case "darwin":
		return newLaunchd(), nil
	default:
		return newStub(), nil
	}
}

// detectLinux tries systemd → openrc → sysv
func detectLinux() (Manager, error) {
	if fileExists("/run/systemd/system") {
		return newSystemd(), nil
	}
	if fileExists("/sbin/openrc") {
		return newOpenRC(), nil
	}
	if fileExists("/etc/init.d") && cmdExists("service") {
		return newSysV(), nil
	}
	return nil, errors.New("no supported init system detected on linux")
}

// fileExists checks if a file or directory exists
func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// cmdExists checks if a command exists in PATH
func cmdExists(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}
