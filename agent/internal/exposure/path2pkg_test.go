package exposure

import "testing"

type fakeResolver struct {
	calls   int
	mapping map[string]PathPkg
}

func (f *fakeResolver) Resolve(paths []string) map[string]PathPkg {
	f.calls++
	out := map[string]PathPkg{}
	for _, p := range paths {
		if v, ok := f.mapping[p]; ok {
			out[p] = v
		}
	}
	return out
}

func TestCachedResolverHitsBackendOnce(t *testing.T) {
	backend := &fakeResolver{
		mapping: map[string]PathPkg{
			"/usr/sbin/nginx": {Pkg: "nginx", Version: "1.24.0"},
		},
	}
	c := NewCachedResolver(backend)

	got := c.Resolve([]string{"/usr/sbin/nginx", "/missing"})
	if got["/usr/sbin/nginx"].Pkg != "nginx" {
		t.Errorf("missing nginx mapping")
	}
	if backend.calls != 1 {
		t.Errorf("calls = %d, want 1", backend.calls)
	}

	// Second call hits cache.
	c.Resolve([]string{"/usr/sbin/nginx"})
	if backend.calls != 1 {
		t.Errorf("calls = %d, want 1 (cached)", backend.calls)
	}
}

const dpkgOutputFixture = `nginx-core: /usr/sbin/nginx
libssl3:amd64: /usr/lib/x86_64-linux-gnu/libssl.so.3
`

func TestParseDpkgSearchOutput(t *testing.T) {
	out := parseDpkgSearchOutput(dpkgOutputFixture)
	if out["/usr/sbin/nginx"].Pkg != "nginx-core" {
		t.Errorf("nginx mapping = %v", out["/usr/sbin/nginx"])
	}
	if out["/usr/lib/x86_64-linux-gnu/libssl.so.3"].Pkg != "libssl3:amd64" {
		t.Errorf("libssl mapping = %v", out["/usr/lib/x86_64-linux-gnu/libssl.so.3"])
	}
}

func TestParseRpmQfOutput(t *testing.T) {
	// rpm -qf with format %{NAME}-%{VERSION} prints one line per path: package-name-version
	output := `nginx-1.24.0
openssl-libs-3.1.1
`
	paths := []string{"/usr/sbin/nginx", "/usr/lib64/libssl.so.3"}
	out := parseRpmQfOutput(paths, output)
	if out["/usr/sbin/nginx"].Pkg != "nginx" || out["/usr/sbin/nginx"].Version != "1.24.0" {
		t.Errorf("nginx mapping = %v", out["/usr/sbin/nginx"])
	}
	if out["/usr/lib64/libssl.so.3"].Pkg != "openssl-libs" || out["/usr/lib64/libssl.so.3"].Version != "3.1.1" {
		t.Errorf("libssl mapping = %v", out["/usr/lib64/libssl.so.3"])
	}
}

func TestParseApkInfoWOutput(t *testing.T) {
	output := `/usr/sbin/nginx is owned by nginx-1.24.0-r0
/usr/lib/libssl.so.3 is owned by openssl-3.1.4-r0
`
	out := parseApkInfoWOutput(output)
	if out["/usr/sbin/nginx"].Pkg != "nginx" || out["/usr/sbin/nginx"].Version != "1.24.0-r0" {
		t.Errorf("nginx mapping = %v", out["/usr/sbin/nginx"])
	}
}
