//go:build linux

package exposure

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

const modulesFixture = `iwlwifi 270336 0 - Live 0x0000000000000000
mac80211 1265664 1 iwlwifi, Live 0x0000000000000000
nf_tables 217088 0 - Live 0x0000000000000000
`

func TestKmodCollectorParsesProcModules(t *testing.T) {
	root := t.TempDir()
	os.WriteFile(filepath.Join(root, "modules"), []byte(modulesFixture), 0o644)
	c := &KmodCollector{ProcRoot: root}
	res := c.Collect(time.Now().Add(time.Second))
	want := map[string]bool{"iwlwifi": false, "mac80211": false, "nf_tables": false}
	for _, k := range res.KernelModules {
		if _, ok := want[k.Name]; ok {
			want[k.Name] = true
		}
	}
	for name, found := range want {
		if !found {
			t.Errorf("module %s not found", name)
		}
	}
}
