//go:build linux

package exposure

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
	"time"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

type KmodCollector struct {
	ProcRoot string // default "/proc"
}

func (c *KmodCollector) Name() string { return "kernel_modules" }

func (c *KmodCollector) Collect(_ time.Time) CollectorResult {
	root := c.ProcRoot
	if root == "" {
		root = "/proc"
	}
	res := CollectorResult{}
	f, err := os.Open(filepath.Join(root, "modules"))
	if err != nil {
		res.Errors = append(res.Errors, err)
		return res
	}
	defer f.Close()

	sc := bufio.NewScanner(f)
	for sc.Scan() {
		fields := strings.Fields(sc.Text())
		if len(fields) < 1 {
			continue
		}
		res.KernelModules = append(res.KernelModules, &pb.KernelModule{
			Name: fields[0],
		})
	}
	if len(res.KernelModules) > DefaultMaxKernelModules {
		res.KernelModules = res.KernelModules[:DefaultMaxKernelModules]
		res.Truncated = true
	}
	return res
}
