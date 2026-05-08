package main

import (
	"encoding/json"
	"fmt"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/hostinfo"
	"github.com/hlhelper/hl-agent/internal/tui"
)

func newInfoCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "info",
		Short: "print host information",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")
			asJSON, _ := cmd.Flags().GetBool("json")

			info := hostinfo.Collect(dir, version)

			if asJSON {
				data, err := json.MarshalIndent(info, "", "  ")
				if err != nil {
					return fmt.Errorf("marshal json: %w", err)
				}
				fmt.Fprintln(cmd.OutOrStdout(), string(data))
				return nil
			}

			// Styled table output.
			rows := [][2]string{
				{"host_id", info.HostID},
				{"grpc_endpoint", info.GrpcEndpoint},
				{"agent_version", info.AgentVersion},
				{"hostname", info.Hostname},
				{"os", info.OS},
				{"os_version", info.OSVersion},
				{"arch", info.Arch},
				{"state_dir", info.StateDir},
				{"binary_path", info.BinaryPath},
			}

			if !info.CertNotAfter.IsZero() {
				rows = append(rows, [2]string{"cert_not_after", info.CertNotAfter.Format("2006-01-02 15:04:05")})
			}

			if info.Sleeping {
				rows = append(rows, [2]string{"sleeping", "true"})
				if !info.SleepUntil.IsZero() {
					rows = append(rows, [2]string{"sleep_until", info.SleepUntil.Format("2006-01-02 15:04:05")})
				}
			}

			tui.Table(cmd.OutOrStdout(), rows)
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	cmd.Flags().Bool("json", false, "output as JSON")

	return cmd
}
