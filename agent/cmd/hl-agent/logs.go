package main

import (
	"fmt"
	"io"
	"os"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/service"
	"github.com/hlhelper/hl-agent/internal/tui"
)

func newLogsCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "logs",
		Short: "show agent service logs",
		RunE: func(cmd *cobra.Command, args []string) error {
			name, _ := cmd.Flags().GetString("name")
			follow, _ := cmd.Flags().GetBool("follow")
			lines, _ := cmd.Flags().GetInt("lines")

			mgr, err := service.Detect()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("detect service manager: %v", err))
				return err
			}

			rc, err := mgr.Logs(name, follow, lines)
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("get logs: %v", err))
				return err
			}
			defer rc.Close()

			// Copy logs to stdout.
			if _, err := io.Copy(cmd.OutOrStdout(), rc); err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("read logs: %v", err))
				return err
			}

			return nil
		},
	}

	cmd.Flags().String("name", "hl-agent", "service unit name")
	cmd.Flags().BoolP("follow", "f", false, "follow log output")
	cmd.Flags().IntP("lines", "n", 50, "number of lines to show")

	return cmd
}
