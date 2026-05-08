package main

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/hostinfo"
	"github.com/hlhelper/hl-agent/internal/service"
	"github.com/hlhelper/hl-agent/internal/tui"
)

func newStatusCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "status",
		Short: "show agent service status",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")
			name, _ := cmd.Flags().GetString("name")
			asJSON, _ := cmd.Flags().GetBool("json")
			watchFlag, _ := cmd.Flags().GetBool("watch")

			mgr, err := service.Detect()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("detect service manager: %v", err))
				return err
			}

			if watchFlag {
				fetch := func() tui.DashboardSnapshot {
					state, stateErr := mgr.Status(name)
					info := hostinfo.Collect(dir, version)
					snap := tui.DashboardSnapshot{
						ServiceState: string(state),
						HostID:       info.HostID,
						GrpcEndpoint: info.GrpcEndpoint,
						AgentVersion: info.AgentVersion,
						Hostname:     info.Hostname,
						OS:           info.OS,
						OSVersion:    info.OSVersion,
						Arch:         info.Arch,
						CertNotAfter: info.CertNotAfter,
						Sleeping:     info.Sleeping,
						SleepUntil:   info.SleepUntil,
						LastUpdated:  time.Now(),
					}
					if stateErr != nil {
						snap.Err = stateErr.Error()
					}
					return snap
				}
				return tui.RunDashboard(cmd.Context(), fetch, 2*time.Second)
			}

			state, err := mgr.Status(name)
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("get status: %v", err))
				return err
			}

			info := hostinfo.Collect(dir, version)

			if asJSON {
				result := map[string]interface{}{
					"service_state": string(state),
					"host_info":     info,
				}
				data, _ := json.MarshalIndent(result, "", "  ")
				fmt.Fprintln(cmd.OutOrStdout(), string(data))
				return nil
			}

			// Styled table.
			tui.Header(cmd.OutOrStdout(), "Service Status")
			tui.Table(cmd.OutOrStdout(), [][2]string{
				{"state", string(state)},
				{"unit", name},
			})

			tui.Header(cmd.OutOrStdout(), "Host Info")
			rows := [][2]string{
				{"host_id", info.HostID},
				{"grpc_endpoint", info.GrpcEndpoint},
				{"agent_version", info.AgentVersion},
			}
			tui.Table(cmd.OutOrStdout(), rows)

			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	cmd.Flags().String("name", "hl-agent", "service unit name")
	cmd.Flags().Bool("json", false, "output as JSON")
	cmd.Flags().Bool("watch", false, "watch live status (TODO)")

	return cmd
}
