//go:build darwin

package exposure

func ReadLoadedLibs(_ string, _ int) []string { return nil }
