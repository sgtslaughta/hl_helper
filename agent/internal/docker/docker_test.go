package docker

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

type fakeRunner struct {
	out  map[string][]byte
	err  map[string]error
	last string
}

func (f *fakeRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	key := name
	if len(args) > 0 {
		key = name + " " + args[0]
	}
	f.last = strings.Join(append([]string{name}, args...), " ")
	return f.out[key], f.err[key]
}

func newClient(out map[string][]byte) (*Client, *fakeRunner) {
	r := &fakeRunner{out: out, err: map[string]error{}}
	return &Client{R: r, Bin: "docker"}, r
}

func TestAvailable(t *testing.T) {
	c, _ := newClient(map[string][]byte{"docker info": []byte("xyz")})
	if !c.Available(context.Background()) {
		t.Fatal("expected available")
	}
}

func TestListContainers(t *testing.T) {
	line := `{"ID":"abc","Image":"nginx","Names":"web","State":"running","Status":"Up","Ports":"80/tcp","CreatedAt":"now","Labels":"hl_helper.managed=true,role=web"}` + "\n"
	c, _ := newClient(map[string][]byte{"docker ps": []byte(line)})
	cts, err := c.ListContainers(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(cts) != 1 || cts[0].Labels["hl_helper.managed"] != "true" {
		t.Fatalf("got %+v", cts)
	}
}

func TestEnsureManagedRejects(t *testing.T) {
	c, _ := newClient(map[string][]byte{"docker inspect": []byte("\n")})
	err := c.Start(context.Background(), "abc", LifecycleOpts{})
	if !errors.Is(err, ErrNotManaged) {
		t.Fatalf("want ErrNotManaged, got %v", err)
	}
}

func TestEnsureManagedForce(t *testing.T) {
	c, _ := newClient(map[string][]byte{"docker start": []byte("ok"), "docker inspect": []byte("\n")})
	if err := c.Start(context.Background(), "abc", LifecycleOpts{Force: true}); err != nil {
		t.Fatal(err)
	}
}

func TestImageDigest(t *testing.T) {
	c, _ := newClient(map[string][]byte{"docker inspect": []byte("nginx@sha256:abc\n")})
	d, err := c.ImageDigest(context.Background(), "nginx")
	if err != nil || d != "sha256:abc" {
		t.Fatalf("got %q %v", d, err)
	}
}

func TestWaitHealthyHealthy(t *testing.T) {
	c, _ := newClient(map[string][]byte{"docker inspect": []byte("running|healthy")})
	ok, err := c.WaitHealthy(context.Background(), "abc", 2*time.Second)
	if err != nil || !ok {
		t.Fatalf("want healthy, got %v %v", ok, err)
	}
}

func TestWaitHealthyUnhealthy(t *testing.T) {
	c, _ := newClient(map[string][]byte{"docker inspect": []byte("running|unhealthy")})
	ok, _ := c.WaitHealthy(context.Background(), "abc", 2*time.Second)
	if ok {
		t.Fatal("expected unhealthy=false")
	}
}
