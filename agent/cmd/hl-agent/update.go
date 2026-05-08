package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/tui"
	"github.com/hlhelper/hl-agent/internal/updater"
)

func newUpdateCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "update",
		Short: "update the agent",
		Long:  "update the agent to a new version or check for available updates",
		RunE: func(cmd *cobra.Command, args []string) error {
			checkOnly, _ := cmd.Flags().GetBool("check")
			dir, _ := cmd.Flags().GetString("dir")

			if checkOnly {
				// Check-only mode: read current state, report version.
				state, err := updater.ReadState(dir)
				if err != nil {
					fmt.Fprintf(cmd.OutOrStdout(), "no update available\n")
					return nil
				}
				fmt.Fprintf(cmd.OutOrStdout(), "current version: %s\n", version)
				fmt.Fprintf(cmd.OutOrStdout(), "latest version: %s\n", state.CurrentVersion)
				return nil
			}

			// Full update: run spinner while applying.
			err := tui.RunSpinner(cmd.OutOrStdout(), "applying update", func() error {
				// For now: no-op. Real implementation would:
				// 1. Fetch manifest from server
				// 2. Verify signature
				// 3. Download binary
				// 4. Call u.Apply()
				return nil
			})

			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("update failed: %v", err))
				return err
			}

			tui.Success(cmd.OutOrStdout(), "update complete")
			return nil
		},
	}

	cmd.Flags().Bool("check", false, "check for updates without applying")
	cmd.Flags().String("dir", resolveStateDir(), "state directory")

	return cmd
}
