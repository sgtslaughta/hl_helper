//go:build linux

package exposure

import (
	"bufio"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// ReadLoadedLibs parses /proc/<pid>/maps and returns deduped lib paths.
// Filters: only paths under /usr/lib, /lib, /opt are returned (excludes
// anonymous mappings, /dev/, /memfd:, etc).
func ReadLoadedLibs(procRoot string, pid int) []string {
	f, err := os.Open(filepath.Join(procRoot, strconv.Itoa(pid), "maps"))
	if err != nil {
		return nil
	}
	defer f.Close()

	seen := make(map[string]struct{})
	var out []string
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		// Format: addr-addr perms offset dev:inode  /path
		idx := strings.Index(line, "/")
		if idx < 0 {
			continue
		}
		path := strings.TrimSpace(line[idx:])
		if !isLibraryPath(path) {
			continue
		}
		if _, ok := seen[path]; ok {
			continue
		}
		seen[path] = struct{}{}
		out = append(out, path)
	}
	return out
}

func isLibraryPath(p string) bool {
	switch {
	case strings.HasPrefix(p, "/usr/lib"),
		strings.HasPrefix(p, "/lib"),
		strings.HasPrefix(p, "/usr/local/lib"),
		strings.HasPrefix(p, "/opt"):
		return strings.Contains(p, ".so")
	}
	return false
}
