package inventory

import (
	"bufio"
	"io"
	"os"
	"os/exec"
	"strings"
)

// CollectOSPackages collects packages from native package managers.
func CollectOSPackages() ([]Pkg, error) {
	var pkgs []Pkg

	// dpkg
	if f, err := os.Open("/var/lib/dpkg/status"); err == nil {
		defer f.Close()
		pkgs = append(pkgs, parseDpkgStatus(f)...)
	}

	// rpm
	if cmd := exec.Command("rpm", "-qa", "--qf", "%{NAME}|%{VERSION}-%{RELEASE}|%{ARCH}\n"); cmd != nil {
		if out, err := cmd.Output(); err == nil {
			pkgs = append(pkgs, parseRPMOutput(string(out))...)
		}
	}

	// pacman
	if fi, err := os.Stat("/var/lib/pacman/local"); err == nil && fi.IsDir() {
		pkgs = append(pkgs, parsePacmanDB()...)
	}

	// apk
	if f, err := os.Open("/lib/apk/db/installed"); err == nil {
		defer f.Close()
		pkgs = append(pkgs, parseAPK(f)...)
	}

	return pkgs, nil
}

// parseDpkgStatus parses /var/lib/dpkg/status format.
func parseDpkgStatus(r io.Reader) []Pkg {
	var pkgs []Pkg
	pkg := Pkg{Ecosystem: "dpkg"}
	var status string

	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Text()

		if line == "" {
			// Entry separator
			if pkg.Name != "" && strings.Contains(status, "install ok installed") {
				pkgs = append(pkgs, pkg)
			}
			pkg = Pkg{Ecosystem: "dpkg"}
			status = ""
			continue
		}

		k, v := parseKV(line)
		switch k {
		case "Package":
			pkg.Name = v
		case "Version":
			pkg.Version = v
		case "Architecture":
			pkg.Arch = v
		case "Status":
			status = v
		}
	}

	// Flush last entry if present
	if pkg.Name != "" && strings.Contains(status, "install ok installed") {
		pkgs = append(pkgs, pkg)
	}

	return pkgs
}

// parseRPMOutput parses rpm -qa output.
func parseRPMOutput(out string) []Pkg {
	var pkgs []Pkg
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.Split(line, "|")
		if len(parts) >= 3 {
			pkgs = append(pkgs, Pkg{
				Ecosystem: "rpm",
				Name:      parts[0],
				Version:   parts[1],
				Arch:      parts[2],
			})
		}
	}
	return pkgs
}

// parsePacmanDB reads from /var/lib/pacman/local.
func parsePacmanDB() []Pkg {
	var pkgs []Pkg
	entries, err := os.ReadDir("/var/lib/pacman/local")
	if err != nil {
		return pkgs
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		descFile := "/var/lib/pacman/local/" + entry.Name() + "/desc"
		f, err := os.Open(descFile)
		if err != nil {
			continue
		}
		defer f.Close()

		pkg := parsePacmanDesc(f)
		if pkg.Name != "" {
			pkg.Ecosystem = "pacman"
			pkgs = append(pkgs, pkg)
		}
	}

	return pkgs
}

// parsePacmanDesc parses a single pacman desc file.
func parsePacmanDesc(r io.Reader) Pkg {
	var pkg Pkg
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Text()
		switch line {
		case "%NAME%":
			if scanner.Scan() {
				pkg.Name = scanner.Text()
			}
		case "%VERSION%":
			if scanner.Scan() {
				pkg.Version = scanner.Text()
			}
		case "%ARCH%":
			if scanner.Scan() {
				pkg.Arch = scanner.Text()
			}
		}
	}
	return pkg
}

// parseAPK parses /lib/apk/db/installed.
func parseAPK(r io.Reader) []Pkg {
	var pkgs []Pkg
	var pkg Pkg

	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			if pkg.Name != "" {
				pkg.Ecosystem = "apk"
				pkgs = append(pkgs, pkg)
				pkg = Pkg{}
			}
			continue
		}

		if strings.HasPrefix(line, "P:") {
			pkg.Name = strings.TrimSpace(line[2:])
		} else if strings.HasPrefix(line, "V:") {
			pkg.Version = strings.TrimSpace(line[2:])
		} else if strings.HasPrefix(line, "A:") {
			pkg.Arch = strings.TrimSpace(line[2:])
		}
	}

	if pkg.Name != "" {
		pkg.Ecosystem = "apk"
		pkgs = append(pkgs, pkg)
	}

	return pkgs
}

// parseKV parses "Key: Value" format.
func parseKV(line string) (string, string) {
	idx := strings.Index(line, ":")
	if idx < 0 {
		return "", ""
	}
	k := strings.TrimSpace(line[:idx])
	v := strings.TrimSpace(line[idx+1:])
	return k, v
}
