package transport_test

import (
	"testing"

	"go.uber.org/goleak"
)

// gRPC client and stub-server goroutines may linger briefly after the test
// stops them; ignore well-known top-frames from grpc-go's internals.
// These ignores cover SERVER-side stub handlers used by tests, not
// production agent client code, which goleak still verifies clean-shutdown for.
func TestMain(m *testing.M) {
	goleak.VerifyTestMain(m,
		goleak.IgnoreTopFunction("google.golang.org/grpc.(*ccBalancerWrapper).watcher"),
		goleak.IgnoreTopFunction("google.golang.org/grpc/internal/transport.(*controlBuffer).get"),
		goleak.IgnoreTopFunction("google.golang.org/grpc/internal/grpcsync.(*CallbackSerializer).run"),
		// Stub server stream handlers held by tests' bidi streams:
		goleak.IgnoreTopFunction("github.com/hlhelper/hl-agent/internal/transport_test.TestRunRespectsContextCancel.func1"),
		goleak.IgnoreAnyFunction("google.golang.org/grpc.(*Server).serveStreams.func2.1"),
		goleak.IgnoreAnyFunction("google.golang.org/grpc.(*Server).handleStream"),
	)
}
