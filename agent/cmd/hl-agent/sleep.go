package main

import (
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/sleep"
	"github.com/hlhelper/hl-agent/internal/tui"
)

func newSleepCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "sleep <duration>",
		Short: "put the agent to sleep",
		Long:  "put the agent to sleep for the specified duration (e.g. 1h, 30m)",
		RunE: func(cmd *cobra.Command, args []string) error {
			if len(args) < 1 {
				return fmt.Errorf("duration required (e.g. 1h, 30m)")
			}

			dir, _ := cmd.Flags().GetString("dir")
			reason, _ := cmd.Flags().GetString("reason")

			durStr := args[0]
			dur, err := time.ParseDuration(durStr)
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("parse duration: %v", err))
				return err
			}

			state, err := sleep.Set(dir, dur, reason)
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("set sleep: %v", err))
				return err
			}

			fmt.Fprintf(cmd.OutOrStdout(), "Agent sleeping until %s\n", state.Until.Format("2006-01-02 15:04:05"))
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	cmd.Flags().String("reason", "", "reason for sleeping")

	return cmd
}

func newResumeCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "resume",
		Short: "resume the agent from sleep",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")

			if err := sleep.Clear(dir); err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("clear sleep: %v", err))
				return err
			}

			tui.Success(cmd.OutOrStdout(), "Agent resumed")
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	return cmd
}
