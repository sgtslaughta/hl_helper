package main

import (
	"fmt"
	"os"
	"runtime"

	"github.com/spf13/cobra"
)

var (
	version = "dev"
	commit  = "none"
	date    = "unknown"
)

var configPath string

func main() {
	if err := newRootCmd().Execute(); err != nil {
		os.Exit(1)
	}
}

func newRootCmd() *cobra.Command {
	root := &cobra.Command{
		Use:   "hl-agent",
		Short: "hl-agent - hardware-locked agent",
		Long:  "hl-agent is a hardware-locked provisioning and management agent.",
	}

	root.PersistentFlags().StringVar(&configPath, "config", "/etc/hl-agent/config.yaml", "path to config file")

	root.AddCommand(
		versionCmd(),
		enrollCmd(),
		serviceCmd(),
		decommissionCmd(),
		rotateSigningKeyCmd(),
	)

	return root
}

func versionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "version",
		Short: "print version information",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Fprintf(cmd.OutOrStdout(), "hl-agent version %s\n", version)
			fmt.Fprintf(cmd.OutOrStdout(), "commit:    %s\n", commit)
			fmt.Fprintf(cmd.OutOrStdout(), "built:     %s\n", date)
			fmt.Fprintf(cmd.OutOrStdout(), "go:        %s\n", runtime.Version())
			return nil
		},
	}
}

func enrollCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "enroll",
		Short: "enroll the agent",
		Long:  "enroll the agent with a server (not yet implemented)",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Fprintf(cmd.OutOrStderr(), "enroll: not yet implemented\n")
			return fmt.Errorf("enroll: not yet implemented")
		},
	}
}

func serviceCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "service",
		Short: "manage the agent service",
		Long:  "manage the agent service (not yet implemented)",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Fprintf(cmd.OutOrStderr(), "service: not yet implemented\n")
			return fmt.Errorf("service: not yet implemented")
		},
	}
}

func decommissionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "decommission",
		Short: "decommission the agent",
		Long:  "decommission the agent (not yet implemented)",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Fprintf(cmd.OutOrStderr(), "decommission: not yet implemented\n")
			return fmt.Errorf("decommission: not yet implemented")
		},
	}
}

func rotateSigningKeyCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "rotate-signing-key",
		Short: "rotate the signing key",
		Long:  "rotate the signing key (not yet implemented)",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Fprintf(cmd.OutOrStderr(), "rotate-signing-key: not yet implemented\n")
			return fmt.Errorf("rotate-signing-key: not yet implemented")
		},
	}
}
