package transport

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

const procNetDevFixture = `Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:   12345     100    0    0    0     0          0         0    12345     100    0    0    0     0       0          0
  eth0: 1000000    1000   2    0    0     0          0         0   500000     500    0    0    0     0       0          0
veth123:    1000      10    0    0    0     0          0         0     1000      10    0    0    0     0       0          0
`

func TestNetIfaceSamplerFirstSampleIsSinceBoot(t *testing.T) {
	root := t.TempDir()
	netDir := filepath.Join(root, "net")
	os.MkdirAll(netDir, 0o755)
	os.WriteFile(filepath.Join(netDir, "dev"), []byte(procNetDevFixture), 0o644)

	s := &NetIfaceSampler{ProcRoot: root}
	out := s.Sample()
	hasEth0 := false
	for _, iface := range out {
		if iface.Name == "eth0" {
			hasEth0 = true
			if !iface.SinceBoot {
				t.Error("first sample should set SinceBoot=true")
			}
			if iface.RxBps != 0 || iface.TxBps != 0 {
				t.Errorf("first sample rates should be 0, got rx=%d tx=%d", iface.RxBps, iface.TxBps)
			}
		}
	}
	if !hasEth0 {
		t.Error("eth0 missing from sample")
	}
}

func TestNetIfaceSamplerComputesDelta(t *testing.T) {
	root := t.TempDir()
	netDir := filepath.Join(root, "net")
	os.MkdirAll(netDir, 0o755)
	os.WriteFile(filepath.Join(netDir, "dev"), []byte(procNetDevFixture), 0o644)

	s := &NetIfaceSampler{ProcRoot: root}
	s.Sample() // First sample primes baseline

	// Bump counters in fixture: eth0 +1MB rx after 1s
	updated := `Inter-|   Receive
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:   12345     100    0    0    0     0          0         0    12345     100    0    0    0     0       0          0
  eth0: 2000000    2000   2    0    0     0          0         0   500000     500    0    0    0     0       0          0
`
	os.WriteFile(filepath.Join(netDir, "dev"), []byte(updated), 0o644)
	time.Sleep(50 * time.Millisecond)
	out := s.Sample()
	for _, iface := range out {
		if iface.Name == "eth0" && iface.SinceBoot {
			t.Error("second sample should not be SinceBoot")
		}
	}
}

func TestNetIfaceSamplerFiltersVirtualInterfaces(t *testing.T) {
	root := t.TempDir()
	netDir := filepath.Join(root, "net")
	os.MkdirAll(netDir, 0o755)
	os.WriteFile(filepath.Join(netDir, "dev"), []byte(procNetDevFixture), 0o644)

	s := &NetIfaceSampler{ProcRoot: root, ExcludeVirtual: true}
	out := s.Sample()
	for _, iface := range out {
		if iface.Name == "veth123" {
			t.Error("veth* should be filtered with ExcludeVirtual=true")
		}
	}
}
