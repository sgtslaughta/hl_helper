package enrollment

import (
	"bufio"
	"os"
	"runtime"
	"strings"
)

// collectHostLabels gathers a small set of facts about the host that the
// server can render in the UI (OS, arch, kernel, agent version). All values
// are best-effort; missing entries are simply omitted.
func collectHostLabels() map[string]string {
	out := map[string]string{
		"os":   runtime.GOOS,
		"arch": runtime.GOARCH,
	}
	if name, version := readOSRelease(); name != "" {
		out["os_pretty"] = name
		if version != "" {
			out["os_version"] = version
		}
	}
	if k := readKernel(); k != "" {
		out["kernel"] = k
	}
	if h, err := os.Hostname(); err == nil {
		out["hostname"] = h
	}
	out["agent_version"] = AgentVersion
	return out
}

// AgentVersion is overridden via -ldflags by the Go build at link time.
// Keep a sane default so dev builds aren't blank in the UI.
var AgentVersion = "dev"

func readOSRelease() (name, version string) {
	f, err := os.Open("/etc/os-release")
	if err != nil {
		return "", ""
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		key, val, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		val = strings.Trim(val, `"`)
		switch key {
		case "PRETTY_NAME":
			name = val
		case "VERSION_ID":
			version = val
		}
	}
	return name, version
}

func readKernel() string {
	b, err := os.ReadFile("/proc/sys/kernel/osrelease")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}
