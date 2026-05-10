//go:build linux

package exposure

import (
	"bufio"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type ProcessCollector struct {
	ProcRoot string // override for tests; default "/proc"
}

func (c *ProcessCollector) Name() string { return "processes" }

func (c *ProcessCollector) Collect(deadline time.Time) CollectorResult {
	root := c.ProcRoot
	if root == "" {
		root = "/proc"
	}
	res := CollectorResult{}

	entries, err := os.ReadDir(root)
	if err != nil {
		res.Errors = append(res.Errors, err)
		return res
	}

	for _, e := range entries {
		if time.Now().After(deadline) {
			res.Truncated = true
			break
		}
		if !e.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(e.Name())
		if err != nil || pid <= 0 {
			continue
		}
		p := readProcess(root, pid)
		if p == nil {
			continue
		}
		res.Processes = append(res.Processes, p)
	}

	procs, truncated := ApplyProcessBudget(res.Processes, DefaultMaxProcesses)
	res.Processes = procs
	if truncated {
		res.Truncated = true
	}
	return res
}

func readProcess(procRoot string, pid int) *pb.Process {
	pidStr := strconv.Itoa(pid)
	exe, _ := os.Readlink(filepath.Join(procRoot, pidStr, "exe"))
	cmdRaw, _ := os.ReadFile(filepath.Join(procRoot, pidStr, "cmdline"))
	cmdline := strings.ReplaceAll(strings.TrimRight(string(cmdRaw), "\x00"), "\x00", " ")

	user := ""
	if f, err := os.Open(filepath.Join(procRoot, pidStr, "status")); err == nil {
		defer f.Close()
		sc := bufio.NewScanner(f)
		for sc.Scan() {
			line := sc.Text()
			if strings.HasPrefix(line, "Uid:") {
				fields := strings.Fields(line)
				if len(fields) >= 2 {
					user = fields[1]
				}
				break
			}
		}
	}

	loadedLibs := ReadLoadedLibs(procRoot, pid)
	loadedLibs, _ = DedupeLibs(loadedLibs, DefaultMaxUniqueLibs)

	return &pb.Process{
		Pid:        uint32(pid),
		ExePath:    exe,
		Cmdline:    cmdline,
		User:       user,
		LoadedLibs: loadedLibs,
	}
}
