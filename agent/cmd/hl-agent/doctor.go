package main

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/tui"
)

func newDoctorCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "doctor",
		Short: "run diagnostics",
		Long:  "run diagnostics to check agent health",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")

			checks := []func(string) checkResult{
				checkManifest,
				checkKeystore,
				checkCert,
				checkServerReach,
				checkClockSkew,
				checkStateDir,
			}

			allPass := true
			for _, check := range checks {
				result := check(dir)
				if result.pass {
					tui.Success(cmd.OutOrStdout(), fmt.Sprintf("%s: %s", result.name, result.msg))
				} else if result.warn {
					tui.Warn(cmd.OutOrStdout(), fmt.Sprintf("%s: %s", result.name, result.msg))
				} else {
					tui.Failure(cmd.OutOrStdout(), fmt.Sprintf("%s: %s", result.name, result.msg))
					allPass = false
				}
			}

			if !allPass {
				return fmt.Errorf("some checks failed")
			}

			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	return cmd
}
