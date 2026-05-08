package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/decom"
	"github.com/hlhelper/hl-agent/internal/service"
	"github.com/hlhelper/hl-agent/internal/tui"
)

func newUninstallCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "uninstall",
		Short: "uninstall the agent service",
		Long:  "uninstall the agent service with optional state management",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")
			purge, _ := cmd.Flags().GetBool("purge")
			keep, _ := cmd.Flags().GetBool("keep")
			name := "hl-agent"

			// Detect service manager.
			mgr, err := service.Detect()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("detect service manager: %v", err))
				return err
			}

			// Determine action: interactive, purge, or keep.
			var action string
			if purge {
				action = "purge"
			} else if keep {
				action = "keep"
			} else {
				// Interactive mode: must be TTY.
				if !isTTY(os.Stdin) {
					tui.Failure(os.Stderr, "interactive uninstall requires a TTY; use --keep or --purge")
					return ErrNotTTY
				}

				// Show interactive selection.
				idx, err := tui.Select("What to do with state?", []tui.Choice{
					{Label: "Keep state (re-enroll later)", Description: "Removes binary + service"},
					{Label: "Wipe everything", Description: "Removes binary + service + state"},
					{Label: "Cancel", Description: "Abort uninstall"},
				})
				if err != nil {
					return err
				}

				switch idx {
				case 0:
					action = "keep"
				case 1:
					action = "purge"
				case 2:
					tui.Info(os.Stdout, "uninstall cancelled")
					os.Exit(2)
				}
			}

			// Stop service.
			err = tui.RunSpinner(os.Stdout, "stopping service", func() error {
				return mgr.Stop(name)
			})
			if err != nil {
				tui.Warn(os.Stdout, fmt.Sprintf("stop service: %v", err))
			}

			// Uninstall unit (service must be uninstalled before state wipe).
			err = tui.RunSpinner(os.Stdout, "removing service unit", func() error {
				return mgr.Uninstall(name)
			})
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("uninstall service: %v", err))
				return err
			}

			// Wipe state if purge action.
			if action == "purge" {
				// Confirm destructive action.
				choice, err := tui.Confirm("Really wipe ALL state? This cannot be undone")
				if err != nil {
					return err
				}

				if choice != tui.ConfirmYes {
					tui.Info(os.Stdout, "state wipe cancelled")
					return nil
				}

				err = tui.RunSpinner(os.Stdout, "wiping state", func() error {
					return decom.Run(decom.Options{Dir: dir, Force: true, Overwrite: 1})
				})
				if err != nil {
					tui.Failure(os.Stderr, fmt.Sprintf("wipe state: %v", err))
					return err
				}
			}

			// Print summary table.
			stateStatus := "kept"
			if action == "purge" {
				stateStatus = "wiped"
			}
			tui.Table(os.Stdout, [][2]string{
				{"Binary", "removed"},
				{"Service", "removed"},
				{"State dir", stateStatus},
			})
			tui.Success(os.Stdout, "uninstallation complete")
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	cmd.Flags().Bool("purge", false, "also wipe all agent state")
	cmd.Flags().Bool("keep", false, "keep state after uninstall")

	return cmd
}
