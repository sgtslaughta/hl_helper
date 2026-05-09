//go:build linux

package exposure

import (
	"bufio"
	"encoding/hex"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

const (
	tcpListen      = "0A"
	tcpEstablished = "01"
)

type SocketCollector struct {
	ProcRoot string // default "/proc"
}

func (c *SocketCollector) Name() string { return "sockets" }

func (c *SocketCollector) Collect(deadline time.Time) CollectorResult {
	root := c.ProcRoot
	if root == "" {
		root = "/proc"
	}
	res := CollectorResult{}

	for _, file := range []struct {
		path  string
		proto string
		ipv6  bool
	}{
		{filepath.Join(root, "net", "tcp"), "tcp", false},
		{filepath.Join(root, "net", "tcp6"), "tcp6", true},
		{filepath.Join(root, "net", "udp"), "udp", false},
		{filepath.Join(root, "net", "udp6"), "udp6", true},
	} {
		listeners, conns, err := parseProcNet(file.path, file.proto, file.ipv6)
		if err != nil {
			res.Errors = append(res.Errors, err)
			continue
		}
		res.Listeners = append(res.Listeners, listeners...)
		res.Connections = append(res.Connections, conns...)
		if time.Now().After(deadline) {
			res.Truncated = true
			break
		}
	}

	listeners, lTrunc := ApplyListenerBudget(res.Listeners, DefaultMaxListeners)
	conns, cTrunc := ApplyConnectionBudget(res.Connections, DefaultMaxConnections)
	res.Listeners = listeners
	res.Connections = conns
	if lTrunc || cTrunc {
		res.Truncated = true
	}
	return res
}

func parseProcNet(path, proto string, ipv6 bool) (
	[]*pb.ListeningSocket, []*pb.Connection, error,
) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer f.Close()

	var listeners []*pb.ListeningSocket
	var conns []*pb.Connection
	sc := bufio.NewScanner(f)
	first := true
	for sc.Scan() {
		if first {
			first = false
			continue
		}
		fields := strings.Fields(sc.Text())
		if len(fields) < 4 {
			continue
		}
		localAddr, localPort, err := decodeAddrPort(fields[1], ipv6)
		if err != nil {
			continue
		}
		remoteAddr, remotePort, _ := decodeAddrPort(fields[2], ipv6)
		state := fields[3]

		switch state {
		case tcpListen:
			listeners = append(listeners, &pb.ListeningSocket{
				Proto: proto, BindAddr: localAddr, Port: localPort,
			})
		case tcpEstablished:
			conns = append(conns, &pb.Connection{
				Proto:      proto,
				LocalAddr:  localAddr,
				LocalPort:  localPort,
				RemoteAddr: remoteAddr,
				RemotePort: remotePort,
				State:      "ESTABLISHED",
			})
		}
	}
	return listeners, conns, sc.Err()
}

func decodeAddrPort(s string, ipv6 bool) (string, uint32, error) {
	parts := strings.SplitN(s, ":", 2)
	if len(parts) != 2 {
		return "", 0, os.ErrInvalid
	}
	addrHex := parts[0]
	portHex := parts[1]
	port64, err := strconv.ParseUint(portHex, 16, 32)
	if err != nil {
		return "", 0, err
	}

	addrBytes, err := hex.DecodeString(addrHex)
	if err != nil {
		return "", 0, err
	}
	// /proc gives little-endian; reverse.
	for i, j := 0, len(addrBytes)-1; i < j; i, j = i+1, j-1 {
		addrBytes[i], addrBytes[j] = addrBytes[j], addrBytes[j]
	}
	var addrStr string
	if ipv6 && len(addrBytes) == 16 {
		addrStr = net.IP(addrBytes).String()
	} else if len(addrBytes) == 4 {
		addrStr = net.IP(addrBytes).String()
	} else {
		addrStr = ""
	}
	return addrStr, uint32(port64), nil
}
