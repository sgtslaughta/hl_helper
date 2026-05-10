//go:build linux

package exposure

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestProcessCollectorParsesProc(t *testing.T) {
	root := t.TempDir()
	// Build a fake /proc/<pid>/ tree
	pidDir := filepath.Join(root, "1234")
	if err := os.MkdirAll(pidDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(pidDir, "comm"), []byte("nginx\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(pidDir, "cmdline"), []byte("nginx\x00-c\x00/etc/nginx.conf\x00"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(pidDir, "status"), []byte("Name:\tnginx\nUid:\t0\t0\t0\t0\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	exeLink := filepath.Join(pidDir, "exe")
	target := filepath.Join(root, "nginx-binary")
	os.WriteFile(target, []byte{}, 0o755)
	if err := os.Symlink(target, exeLink); err != nil {
		t.Fatal(err)
	}

	c := &ProcessCollector{ProcRoot: root}
	res := c.Collect(time.Now().Add(5 * time.Second))
	if len(res.Processes) != 1 {
		t.Fatalf("want 1 process, got %d", len(res.Processes))
	}
	p := res.Processes[0]
	if p.Pid != 1234 {
		t.Errorf("pid = %d", p.Pid)
	}
	if p.ExePath != target {
		t.Errorf("exe = %q want %q", p.ExePath, target)
	}
	if p.Cmdline != "nginx -c /etc/nginx.conf" {
		t.Errorf("cmdline = %q", p.Cmdline)
	}
	if p.User != "0" {
		t.Errorf("user = %q", p.User)
	}
}
