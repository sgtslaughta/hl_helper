package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/manifest"
	"github.com/hlhelper/hl-agent/internal/tui"
)

// newSetEndpointCmd updates the gRPC endpoint stored in the manifest.
// Use this when the server's gRPC address changes (proxy reconfig, port move,
// DNS change) but the same server identity is preserved. If the server
// identity changes, re-run `hl-agent enroll` instead.
func newSetEndpointCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "set-endpoint <host:port>",
		Short: "update the gRPC endpoint in the local manifest",
		Long: "update the gRPC endpoint stored in the local manifest. " +
			"Use when the server's gRPC address changes but the server " +
			"identity (signing key, host_id binding) is unchanged. " +
			"For a server-identity change, re-enroll instead.",
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")
			endpoint := strings.TrimSpace(args[0])

			if endpoint == "" {
				return fmt.Errorf("endpoint must not be empty")
			}
			if !strings.Contains(endpoint, ":") {
				return fmt.Errorf("endpoint must include a port (host:port)")
			}

			m, err := manifest.Load(dir)
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("load manifest: %v", err))
				return err
			}

			old := m.GRPCEndpoint
			m.GRPCEndpoint = endpoint
			if err := m.Save(dir); err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("save manifest: %v", err))
				return err
			}

			tui.Success(cmd.OutOrStdout(), fmt.Sprintf("endpoint updated: %s → %s", old, endpoint))
			tui.Info(cmd.OutOrStdout(), "restart the agent service to apply: hl-agent restart")
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	return cmd
}

// newShowEndpointCmd is a styled alias of get-endpoint that adds context.
func newShowEndpointCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "show-endpoint",
		Short: "show the configured gRPC endpoint with context",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")
			m, err := manifest.Load(dir)
			if err != nil {
				return fmt.Errorf("load manifest: %w", err)
			}
			tui.KeyValue(cmd.OutOrStdout(), "host_id", m.HostID)
			tui.KeyValue(cmd.OutOrStdout(), "grpc_endpoint", m.GRPCEndpoint)
			return nil
		},
	}
	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	return cmd
}
