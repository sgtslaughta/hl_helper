//go:build linux

package exposure

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

const tcpFixture = `  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F40 00000000:0000 0A 00000000:00000000 00:00000000 00000000   100        0 12345 1 ffff
   1: 00000000:01BB 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 67890 1 ffff
   2: 0100007F:1A0A C0A801C8:0050 01 00000000:00000000 00:00000000 00000000   100        0 99999 1 ffff
`

func TestSocketCollectorParsesListeners(t *testing.T) {
	root := t.TempDir()
	netDir := filepath.Join(root, "net")
	os.MkdirAll(netDir, 0o755)
	os.WriteFile(filepath.Join(netDir, "tcp"), []byte(tcpFixture), 0o644)
	os.WriteFile(filepath.Join(netDir, "tcp6"), []byte(""), 0o644)
	os.WriteFile(filepath.Join(netDir, "udp"), []byte(""), 0o644)
	os.WriteFile(filepath.Join(netDir, "udp6"), []byte(""), 0o644)

	c := &SocketCollector{ProcRoot: root}
	res := c.Collect(time.Now().Add(5 * time.Second))

	// Two listeners (st=0A): 127.0.0.1:8000 (port 0x1F40) and 0.0.0.0:443 (0x01BB)
	wantPorts := map[uint32]bool{8000: false, 443: false}
	for _, l := range res.Listeners {
		if _, ok := wantPorts[l.Port]; ok {
			wantPorts[l.Port] = true
		}
	}
	for p, found := range wantPorts {
		if !found {
			t.Errorf("listener on port %d not found", p)
		}
	}

	// One connection (st=01 = ESTABLISHED)
	if len(res.Connections) != 1 {
		t.Errorf("connections = %d, want 1", len(res.Connections))
	}
}
