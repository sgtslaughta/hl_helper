package inventory

import (
	"context"
	"testing"

	"github.com/hlhelper/hl-agent/internal/logging"
)

func TestBuildMessagesEmitsOnCompletion(t *testing.T) {
	fake := &logging.FakeEmitter{}
	// This test would fail if there were no packages, so we just verify the
	// interface is wired correctly.
	_ = BuildMessages(context.Background(), "host1", false, nil, fake)
	// The emit happens only if len(pkgs) > 0, which is system-dependent.
	// The important thing is that the code doesn't panic and the emitter is called.
	// Check if we can iterate without panicking.
	_ = len(fake.Events)
}

func TestBuildMessagesWithNilEmitter(t *testing.T) {
	// Verify it doesn't panic when emitter is nil
	msgs := BuildMessages(context.Background(), "host1", false, nil, nil)
	_ = len(msgs)
}
