package inventory

import (
	"bufio"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// CollectLangPackages collects packages from language-specific managers.
func CollectLangPackages(roots []string) ([]Pkg, error) {
	var pkgs []Pkg

	for _, root := range roots {
		// pip
		pipPkgs, _ := collectPip(root)
		pkgs = append(pkgs, pipPkgs...)

		// npm
		npmPkgs, _ := collectNPM(root)
		pkgs = append(pkgs, npmPkgs...)

		// cargo
		cargoPkgs, _ := collectCargo(root)
		pkgs = append(pkgs, cargoPkgs...)
	}

	return pkgs, nil
}

// collectPip scans for site-packages dist-info directories.
func collectPip(root string) ([]Pkg, error) {
	var pkgs []Pkg
	sitePackages := filepath.Join(root, "site-packages")

	entries, err := os.ReadDir(sitePackages)
	if err != nil {
		return pkgs, nil
	}

	for _, entry := range entries {
		if !entry.IsDir() || !strings.HasSuffix(entry.Name(), ".dist-info") {
			continue
		}

		metaFile := filepath.Join(sitePackages, entry.Name(), "METADATA")
		f, err := os.Open(metaFile)
		if err != nil {
			continue
		}
		defer f.Close()

		pkg := parsePipMetadata(f)
		if pkg.Name != "" {
			pkg.Ecosystem = "pip"
			pkgs = append(pkgs, pkg)
		}
	}

	return pkgs, nil
}

// parsePipMetadata extracts Name and Version from METADATA.
func parsePipMetadata(r io.Reader) Pkg {
	var pkg Pkg
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "Name:") {
			pkg.Name = strings.TrimSpace(line[5:])
		} else if strings.HasPrefix(line, "Version:") {
			pkg.Version = strings.TrimSpace(line[8:])
		}
		if pkg.Name != "" && pkg.Version != "" {
			break
		}
	}
	return pkg
}

// collectNPM scans for node_modules packages.
func collectNPM(root string) ([]Pkg, error) {
	var pkgs []Pkg
	nodeModules := filepath.Join(root, "node_modules")

	entries, err := os.ReadDir(nodeModules)
	if err != nil {
		return pkgs, nil
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		pkgJSON := filepath.Join(nodeModules, entry.Name(), "package.json")
		f, err := os.Open(pkgJSON)
		if err != nil {
			continue
		}
		defer f.Close()

		var data struct {
			Name    string `json:"name"`
			Version string `json:"version"`
		}
		if err := json.NewDecoder(f).Decode(&data); err != nil {
			continue
		}

		if data.Name != "" {
			pkgs = append(pkgs, Pkg{
				Ecosystem: "npm",
				Name:      data.Name,
				Version:   data.Version,
			})
		}
	}

	return pkgs, nil
}

// collectCargo scans ~/.cargo/registry/src for package directories.
func collectCargo(root string) ([]Pkg, error) {
	var pkgs []Pkg
	cargoSrc := filepath.Join(root, ".cargo", "registry", "src")

	entries, err := os.ReadDir(cargoSrc)
	if err != nil {
		return pkgs, nil
	}

	for _, srcDir := range entries {
		if !srcDir.IsDir() {
			continue
		}

		srcPath := filepath.Join(cargoSrc, srcDir.Name())
		pkgEntries, err := os.ReadDir(srcPath)
		if err != nil {
			continue
		}

		for _, pkgEntry := range pkgEntries {
			if !pkgEntry.IsDir() {
				continue
			}

			// dirname is <name>-<version>
			name, version := parseCargoDir(pkgEntry.Name())
			if name != "" {
				pkgs = append(pkgs, Pkg{
					Ecosystem: "cargo",
					Name:      name,
					Version:   version,
				})
			}
		}
	}

	return pkgs, nil
}

// parseCargoDir extracts name and version from "name-version" format.
func parseCargoDir(dirname string) (string, string) {
	// Find last '-' and split
	idx := strings.LastIndexByte(dirname, '-')
	if idx < 0 || idx == 0 || idx == len(dirname)-1 {
		return "", ""
	}
	return dirname[:idx], dirname[idx+1:]
}
