package exposure

import (
	"bufio"
	"os/exec"
	"regexp"
	"strings"
	"sync"
)

type PathPkg struct {
	Pkg     string
	Version string
}

type Resolver interface {
	Resolve(paths []string) map[string]PathPkg
}

// CachedResolver wraps a Resolver with per-scan in-memory cache.
type CachedResolver struct {
	backend Resolver
	mu      sync.Mutex
	cache   map[string]PathPkg
}

func NewCachedResolver(backend Resolver) *CachedResolver {
	return &CachedResolver{backend: backend, cache: map[string]PathPkg{}}
}

func (c *CachedResolver) Resolve(paths []string) map[string]PathPkg {
	c.mu.Lock()
	missing := make([]string, 0, len(paths))
	for _, p := range paths {
		if _, ok := c.cache[p]; !ok {
			missing = append(missing, p)
		}
	}
	c.mu.Unlock()

	if len(missing) > 0 {
		got := c.backend.Resolve(missing)
		c.mu.Lock()
		for p, v := range got {
			c.cache[p] = v
		}
		c.mu.Unlock()
	}

	out := make(map[string]PathPkg, len(paths))
	c.mu.Lock()
	for _, p := range paths {
		if v, ok := c.cache[p]; ok {
			out[p] = v
		}
	}
	c.mu.Unlock()
	return out
}

// DpkgResolver shells dpkg -S to find package ownership
type DpkgResolver struct{}

func (d *DpkgResolver) Resolve(paths []string) map[string]PathPkg {
	if len(paths) == 0 {
		return nil
	}
	// dpkg -S exits 1 if ANY path is not owned by an installed pkg, but it
	// still writes successful matches to stdout. Capture stdout regardless
	// of exit status; only bail if we got nothing.
	args := append([]string{"-S"}, paths...)
	cmd := exec.Command("dpkg", args...)
	out, _ := cmd.Output() // ignore ExitError; partial stdout is useful
	if len(out) == 0 {
		return nil
	}
	return parseDpkgSearchOutput(string(out))
}

func parseDpkgSearchOutput(s string) map[string]PathPkg {
	out := map[string]PathPkg{}
	sc := bufio.NewScanner(strings.NewReader(s))
	for sc.Scan() {
		line := sc.Text()
		idx := strings.Index(line, ": ")
		if idx < 0 {
			continue
		}
		pkg := strings.TrimSpace(line[:idx])
		path := strings.TrimSpace(line[idx+2:])
		out[path] = PathPkg{Pkg: pkg}
	}
	return out
}

// RpmResolver shells rpm -qf to find package ownership
type RpmResolver struct{}

func (r *RpmResolver) Resolve(paths []string) map[string]PathPkg {
	if len(paths) == 0 {
		return nil
	}
	args := append([]string{"-qf", "--qf", "%{NAME}-%{VERSION}\n"}, paths...)
	out, _ := exec.Command("rpm", args...).Output() // ignore ExitError
	if len(out) == 0 {
		return nil
	}
	return parseRpmQfOutput(paths, string(out))
}

func parseRpmQfOutput(paths []string, out string) map[string]PathPkg {
	lines := strings.Split(strings.TrimRight(out, "\n"), "\n")
	res := map[string]PathPkg{}
	if len(lines) != len(paths) {
		// rpm output is paired with input order; if mismatch, abort.
		return nil
	}
	re := regexp.MustCompile(`^(.+)-([^-]+)$`)
	for i, ln := range lines {
		m := re.FindStringSubmatch(ln)
		if m != nil {
			res[paths[i]] = PathPkg{Pkg: m[1], Version: m[2]}
		}
	}
	return res
}

// ApkResolver shells apk info -W to find package ownership
type ApkResolver struct{}

func (a *ApkResolver) Resolve(paths []string) map[string]PathPkg {
	if len(paths) == 0 {
		return nil
	}
	args := append([]string{"info", "-W"}, paths...)
	out, _ := exec.Command("apk", args...).Output() // ignore ExitError
	if len(out) == 0 {
		return nil
	}
	return parseApkInfoWOutput(string(out))
}

var apkRe = regexp.MustCompile(`^(.*) is owned by (.+)-([^-]+-r\d+)$`)

func parseApkInfoWOutput(s string) map[string]PathPkg {
	out := map[string]PathPkg{}
	sc := bufio.NewScanner(strings.NewReader(s))
	for sc.Scan() {
		m := apkRe.FindStringSubmatch(sc.Text())
		if m != nil {
			out[m[1]] = PathPkg{Pkg: m[2], Version: m[3]}
		}
	}
	return out
}

// AutoResolver picks the appropriate backend based on what's installed.
func AutoResolver() Resolver {
	if _, err := exec.LookPath("dpkg"); err == nil {
		return &DpkgResolver{}
	}
	if _, err := exec.LookPath("rpm"); err == nil {
		return &RpmResolver{}
	}
	if _, err := exec.LookPath("apk"); err == nil {
		return &ApkResolver{}
	}
	return &nopResolver{}
}

type nopResolver struct{}

func (n *nopResolver) Resolve(_ []string) map[string]PathPkg { return nil }
