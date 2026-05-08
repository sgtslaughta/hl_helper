package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/service"
	"github.com/hlhelper/hl-agent/internal/tui"
)

func newStartCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "start",
		Short: "start the agent service",
		RunE: func(cmd *cobra.Command, args []string) error {
			name, _ := cmd.Flags().GetString("name")

			mgr, err := service.Detect()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("detect service manager: %v", err))
				return err
			}

			if err := mgr.Start(name); err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("start %s: %v", name, err))
				return err
			}

			tui.Success(os.Stdout, fmt.Sprintf("%s started", name))
			return nil
		},
	}

	cmd.Flags().String("name", "hl-agent", "service unit name")
	return cmd
}

func newStopCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "stop",
		Short: "stop the agent service",
		RunE: func(cmd *cobra.Command, args []string) error {
			name, _ := cmd.Flags().GetString("name")

			mgr, err := service.Detect()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("detect service manager: %v", err))
				return err
			}

			if err := mgr.Stop(name); err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("stop %s: %v", name, err))
				return err
			}

			tui.Success(os.Stdout, fmt.Sprintf("%s stopped", name))
			return nil
		},
	}

	cmd.Flags().String("name", "hl-agent", "service unit name")
	return cmd
}

func newRestartCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "restart",
		Short: "restart the agent service",
		RunE: func(cmd *cobra.Command, args []string) error {
			name, _ := cmd.Flags().GetString("name")

			mgr, err := service.Detect()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("detect service manager: %v", err))
				return err
			}

			if err := mgr.Restart(name); err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("restart %s: %v", name, err))
				return err
			}

			tui.Success(os.Stdout, fmt.Sprintf("%s restarted", name))
			return nil
		},
	}

	cmd.Flags().String("name", "hl-agent", "service unit name")
	return cmd
}
