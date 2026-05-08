package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"golang.org/x/term"
	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/hostinfo"
	"github.com/hlhelper/hl-agent/internal/manifest"
)

// ErrNotTTY indicates that interactive mode requires a TTY.
var ErrNotTTY = errors.New("not a TTY")

func newGetHostIDCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "get-host-id",
		Short: "print the host ID",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")

			info := hostinfo.Collect(dir, version)
			if info.HostID == "" {
				fmt.Fprintf(cmd.ErrOrStderr(), "host_id not found\n")
				return fmt.Errorf("host_id empty")
			}

			fmt.Fprintln(cmd.OutOrStdout(), info.HostID)
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	return cmd
}

func newGetEndpointCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "get-endpoint",
		Short: "print the gRPC endpoint",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")

			info := hostinfo.Collect(dir, version)
			fmt.Fprintln(cmd.OutOrStdout(), info.GrpcEndpoint)
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	return cmd
}

func newGetConfigCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "get-config",
		Short: "print path to config and its contents",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")

			// Print config file path.
			configPath := filepath.Join(dir, "manifest.json")
			fmt.Fprintf(cmd.OutOrStdout(), "config: %s\n", configPath)

			// Load and print manifest.
			m, err := manifest.Load(dir)
			if err != nil {
				// Best-effort: don't fail if manifest missing
				fmt.Fprintf(cmd.ErrOrStderr(), "warn: load manifest: %v\n", err)
				return nil
			}

			// Print manifest fields.
			fmt.Fprintf(cmd.OutOrStdout(), "host_id:   %s\n", m.HostID)
			fmt.Fprintf(cmd.OutOrStdout(), "endpoint:  %s\n", m.GRPCEndpoint)
			fmt.Fprintf(cmd.OutOrStdout(), "max_risk:  %s\n", m.MaxRisk)
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	return cmd
}

func resolveStateDir() string {
	if dir := os.Getenv("HL_STATE_DIR"); dir != "" {
		return dir
	}
	return "/var/lib/hl-agent"
}

// isTTY reports whether the given file is a TTY.
func isTTY(f *os.File) bool {
	return term.IsTerminal(int(f.Fd()))
}
