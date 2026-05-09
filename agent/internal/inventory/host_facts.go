package inventory

import (
	"bufio"
	"io"
	"os"
	"strconv"
	"strings"
)

// CollectHostFacts collects sshd config, sysctl, mounts, and file permissions.
func CollectHostFacts() (Facts, error) {
	facts := Facts{
		SSHD:    make(map[string]string),
		Sysctl:  make(map[string]string),
		FsPerms: make(map[string]string),
	}

	// sshd_config
	if f, err := os.Open("/etc/ssh/sshd_config"); err == nil {
		defer f.Close()
		facts.SSHD = parseSSHDConfig(f)
	}

	// sysctl
	facts.Sysctl = collectSysctl()

	// mounts
	if f, err := os.Open("/proc/mounts"); err == nil {
		defer f.Close()
		facts.Mounts = readLines(f)
	}

	// fs_perms
	facts.FsPerms = collectFsPerms()

	return facts, nil
}

// parseSSHDConfig parses sshd_config format (key value pairs, comments, last-wins).
func parseSSHDConfig(r io.Reader) map[string]string {
	cfg := make(map[string]string)
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		// Parse "Key Value" format
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			key := strings.ToLower(parts[0])
			value := strings.ToLower(parts[1])
			cfg[key] = value
		}
	}
	return cfg
}

// collectSysctl reads selected sysctl values from /proc/sys.
func collectSysctl() map[string]string {
	sysctl := make(map[string]string)

	paths := []string{
		"kernel/randomize_va_space",
		"net/ipv4/conf/all/rp_filter",
		"net/ipv4/conf/all/accept_redirects",
		"kernel/kptr_restrict",
		"kernel/dmesg_restrict",
		"fs/protected_hardlinks",
		"fs/protected_symlinks",
	}

	for _, path := range paths {
		val, err := os.ReadFile("/proc/sys/" + path)
		if err != nil {
			continue
		}
		// Map key is dotted form
		dotted := strings.ReplaceAll(path, "/", ".")
		sysctl[dotted] = strings.TrimSpace(string(val))
	}

	return sysctl
}

// readLines reads all lines from a file.
func readLines(r io.Reader) []string {
	var lines []string
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	return lines
}

// collectFsPerms stats files and records permissions.
func collectFsPerms() map[string]string {
	perms := make(map[string]string)

	paths := []string{
		"/etc/shadow",
		"/etc/passwd",
		"/etc/sudoers",
		"/root",
	}

	for _, path := range paths {
		info, err := os.Stat(path)
		if err != nil {
			continue
		}
		// Store mode as octal string
		mode := info.Mode().Perm()
		octal := "0" + strconv.FormatInt(int64(mode), 8)
		perms[path] = octal
	}

	return perms
}
