//go:build linux

package exposure

import (
	"os"
	"path/filepath"
	"testing"
)

const mapsFixture = `7f1234000000-7f1234001000 r--p 00000000 fd:00 12345 /usr/lib/x86_64-linux-gnu/libssl.so.3
7f1234001000-7f1234050000 r-xp 00001000 fd:00 12345 /usr/lib/x86_64-linux-gnu/libssl.so.3
7f1234050000-7f1234060000 r--p 00050000 fd:00 12345 /usr/lib/x86_64-linux-gnu/libssl.so.3
7f1234100000-7f1234200000 r-xp 00000000 fd:00 67890 /usr/lib/x86_64-linux-gnu/libcrypto.so.3
7f1234300000-7f1234400000 rw-p 00000000 00:00 0
`

func TestReadLoadedLibsDeduplicates(t *testing.T) {
	root := t.TempDir()
	pidDir := filepath.Join(root, "1234")
	os.MkdirAll(pidDir, 0o755)
	os.WriteFile(filepath.Join(pidDir, "maps"), []byte(mapsFixture), 0o644)

	libs := ReadLoadedLibs(root, 1234)
	want := map[string]bool{
		"/usr/lib/x86_64-linux-gnu/libssl.so.3":    true,
		"/usr/lib/x86_64-linux-gnu/libcrypto.so.3": true,
	}
	if len(libs) != len(want) {
		t.Errorf("got %d libs, want %d: %v", len(libs), len(want), libs)
	}
	for _, l := range libs {
		if !want[l] {
			t.Errorf("unexpected lib: %q", l)
		}
	}
}
