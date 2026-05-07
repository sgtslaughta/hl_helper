// Package survey collects a one-shot host hardware/OS inventory.
package survey

import (
	"context"
	"net"
	"os"
	"strings"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/host"
	"github.com/shirou/gopsutil/v3/mem"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

var skippedFs = map[string]struct{}{
	"tmpfs": {}, "devtmpfs": {}, "overlay": {}, "squashfs": {},
	"proc": {}, "sysfs": {}, "cgroup": {}, "cgroup2": {},
	"devpts": {}, "mqueue": {}, "fuse.gvfsd-fuse": {},
	"autofs": {}, "binfmt_misc": {}, "tracefs": {}, "debugfs": {},
	"securityfs": {}, "pstore": {}, "bpf": {}, "ramfs": {},
}

// Collect builds a HostSurvey for the provided hostID. Best-effort: returns
// the most complete survey possible even when individual probes fail.
func Collect(ctx context.Context, hostID string) (*pb.HostSurvey, error) {
	s := &pb.HostSurvey{
		HostId:      hostID,
		CollectedAt: timestamppb.Now(),
	}

	if info, err := host.InfoWithContext(ctx); err == nil {
		s.Os = info.OS
		s.OsVersion = info.PlatformVersion
		s.Kernel = info.KernelVersion
		s.Arch = info.KernelArch
		s.Virt = info.VirtualizationSystem
	}

	if cpus, err := cpu.InfoWithContext(ctx); err == nil && len(cpus) > 0 {
		s.CpuModel = cpus[0].ModelName
	}
	if n, err := cpu.CountsWithContext(ctx, false); err == nil {
		s.CpuCores = uint32(n)
	}
	if n, err := cpu.CountsWithContext(ctx, true); err == nil {
		s.CpuThreads = uint32(n)
	}

	if vm, err := mem.VirtualMemoryWithContext(ctx); err == nil {
		s.MemTotalBytes = vm.Total
	}

	if parts, err := disk.PartitionsWithContext(ctx, false); err == nil {
		for _, p := range parts {
			if _, skip := skippedFs[p.Fstype]; skip {
				continue
			}
			d := &pb.Disk{
				Device: p.Device,
				Mount:  p.Mountpoint,
				Fstype: p.Fstype,
			}
			if u, err := disk.UsageWithContext(ctx, p.Mountpoint); err == nil {
				d.SizeBytes = u.Total
			}
			s.Disks = append(s.Disks, d)
		}
	}

	if ifaces, err := net.Interfaces(); err == nil {
		for _, i := range ifaces {
			if i.Flags&net.FlagLoopback != 0 || i.Flags&net.FlagUp == 0 {
				continue
			}
			n := &pb.Nic{
				Name: i.Name,
				Mac:  i.HardwareAddr.String(),
			}
			if addrs, err := i.Addrs(); err == nil {
				for _, a := range addrs {
					ipStr, _, err := net.ParseCIDR(a.String())
					if err != nil {
						continue
					}
					ip := ipStr.String()
					if ipStr.To4() != nil {
						n.Ipv4 = append(n.Ipv4, ip)
					} else {
						n.Ipv6 = append(n.Ipv6, ip)
					}
				}
			}
			s.Nics = append(s.Nics, n)
		}
	}

	s.BiosVendor = readDmi("bios_vendor")
	s.BiosVersion = readDmi("bios_version")
	s.BoardVendor = readDmi("board_vendor")
	s.BoardProduct = readDmi("board_name")

	return s, nil
}

func readDmi(field string) string {
	b, err := os.ReadFile("/sys/class/dmi/id/" + field)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}
