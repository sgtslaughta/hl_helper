package hostinfo

import (
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/manifest"
)

// Collect reads local state and returns a HostInfo snapshot. Best-effort —
// missing files leave fields zero-valued, never errors out.
// agentVersion is passed in by caller (it's a build-time ldflag in main).
func Collect(stateDir, agentVersion string) HostInfo {
	info := HostInfo{
		StateDir:     stateDir,
		AgentVersion: agentVersion,
	}

	// Hostname: os.Hostname()
	if hostname, err := os.Hostname(); err == nil {
		info.Hostname = hostname
	}

	// OS/Arch: runtime.GOOS, runtime.GOARCH
	info.OS = runtime.GOOS
	info.Arch = runtime.GOARCH

	// BinaryPath: os.Executable()
	if exe, err := os.Executable(); err == nil {
		info.BinaryPath = exe
	}

	// HostID/GrpcEndpoint: read manifest
	if m, err := manifest.Load(stateDir); err == nil {
		info.HostID = m.HostID
		info.GrpcEndpoint = m.GRPCEndpoint
	}

	// OSVersion: best-effort read /etc/os-release on linux for VERSION_ID;
	// on darwin use `sw_vers -productVersion`; never error
	info.OSVersion = readOSVersion()

	// CertNotAfter: open keystore, read agent cert, x509.ParseCertificate, set NotAfter.
	// If anything fails, leave zero.
	info.CertNotAfter = readCertNotAfter(stateDir)

	// Sleeping/SleepUntil: check filesystem for <stateDir>/sleep.json
	info.Sleeping, info.SleepUntil = readSleepState(stateDir)

	return info
}

func readOSVersion() string {
	switch runtime.GOOS {
	case "linux":
		// Try to read /etc/os-release for VERSION_ID
		data, err := os.ReadFile("/etc/os-release")
		if err != nil {
			return ""
		}
		for _, line := range strings.Split(string(data), "\n") {
			if strings.HasPrefix(line, "VERSION_ID=") {
				return strings.Trim(strings.TrimPrefix(line, "VERSION_ID="), "\"")
			}
		}
	case "darwin":
		// Use `sw_vers -productVersion`
		cmd := exec.Command("sw_vers", "-productVersion")
		out, err := cmd.Output()
		if err == nil {
			return strings.TrimSpace(string(out))
		}
	}
	return ""
}

func readCertNotAfter(stateDir string) time.Time {
	// Open keystore
	ks, err := keystore.OpenFile(stateDir)
	if err != nil {
		return time.Time{}
	}

	// Read cert PEM
	certPath := filepath.Join(ks.Dir(), "tls.crt")
	certData, err := os.ReadFile(certPath)
	if err != nil {
		return time.Time{}
	}

	// Parse PEM
	block, _ := pem.Decode(certData)
	if block == nil {
		return time.Time{}
	}

	// Parse x509 certificate
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return time.Time{}
	}

	return cert.NotAfter
}

func readSleepState(stateDir string) (bool, time.Time) {
	sleepPath := filepath.Join(stateDir, "sleep.json")
	data, err := os.ReadFile(sleepPath)
	if err != nil {
		return false, time.Time{}
	}

	var sleepData struct {
		Until time.Time `json:"until"`
	}
	if err := json.Unmarshal(data, &sleepData); err != nil {
		return false, time.Time{}
	}

	// Sleeping = !Until.IsZero() && time.Now().Before(Until)
	if sleepData.Until.IsZero() {
		return false, time.Time{}
	}

	isSleeping := time.Now().Before(sleepData.Until)
	return isSleeping, sleepData.Until
}
