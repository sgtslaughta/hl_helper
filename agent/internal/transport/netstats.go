package transport

import (
	"bufio"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

var virtualIfaceRe = regexp.MustCompile(`^(veth|cali|cni|docker[0-9])`)

type ifaceSnapshot struct {
	rxBytes uint64
	txBytes uint64
	rxErr   uint64
	txErr   uint64
	at      time.Time
}

type NetIfaceSampler struct {
	ProcRoot       string // default "/proc"
	ExcludeVirtual bool

	mu   sync.Mutex
	last map[string]ifaceSnapshot
}

func (s *NetIfaceSampler) Sample() []*pb.NetInterface {
	root := s.ProcRoot
	if root == "" {
		root = "/proc"
	}
	f, err := os.Open(filepath.Join(root, "net", "dev"))
	if err != nil {
		return nil
	}
	defer f.Close()

	now := time.Now()
	current := map[string]ifaceSnapshot{}
	out := []*pb.NetInterface{}

	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		colon := strings.Index(line, ":")
		if colon <= 0 {
			continue
		}
		name := strings.TrimSpace(line[:colon])
		if s.ExcludeVirtual && virtualIfaceRe.MatchString(name) {
			continue
		}
		fields := strings.Fields(line[colon+1:])
		if len(fields) < 16 {
			continue
		}
		rxBytes, _ := strconv.ParseUint(fields[0], 10, 64)
		rxErr, _ := strconv.ParseUint(fields[2], 10, 64)
		txBytes, _ := strconv.ParseUint(fields[8], 10, 64)
		txErr, _ := strconv.ParseUint(fields[10], 10, 64)
		current[name] = ifaceSnapshot{
			rxBytes: rxBytes, txBytes: txBytes,
			rxErr: rxErr, txErr: txErr, at: now,
		}
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	for name, cur := range current {
		prev, ok := s.last[name]
		iface := &pb.NetInterface{Name: name, Up: true}
		if !ok {
			iface.SinceBoot = true
		} else {
			dt := cur.at.Sub(prev.at).Seconds()
			if dt > 0 {
				iface.RxBps = uint64(float64(cur.rxBytes-prev.rxBytes) / dt)
				iface.TxBps = uint64(float64(cur.txBytes-prev.txBytes) / dt)
			}
			iface.RxErrors = cur.rxErr
			iface.TxErrors = cur.txErr
		}
		out = append(out, iface)
	}

	s.last = current
	return out
}
