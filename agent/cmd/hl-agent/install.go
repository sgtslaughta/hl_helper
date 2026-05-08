package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/enrollment"
	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/service"
	"github.com/hlhelper/hl-agent/internal/tui"
)

func newInstallCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "install",
		Short: "install the agent service",
		Long:  "install the agent service (interactive wizard or unattended mode)",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")
			server, _ := cmd.Flags().GetString("server")
			token, _ := cmd.Flags().GetString("token")
			hostname, _ := cmd.Flags().GetString("hostname")
			unattended, _ := cmd.Flags().GetBool("unattended")

			// Detect service manager.
			mgr, err := service.Detect()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("detect service manager: %v", err))
				return err
			}

			tui.Info(os.Stdout, fmt.Sprintf("detected %s", mgr.Kind()))

			// If not unattended and server/token not both provided, use wizard.
			if !unattended && (server == "" || token == "") {
				wizRes, err := tui.RunWizard(tui.WizardConfig{
					InitKind: mgr.Kind(),
					Server:   server,
					Token:    token,
					Hostname: hostname,
				}, os.Stdout)
				if err != nil {
					tui.Failure(os.Stderr, fmt.Sprintf("wizard cancelled: %v", err))
					return err
				}
				server = wizRes.Server
				token = wizRes.Token
				hostname = wizRes.Hostname
			}

			// Create keystore dir.
			if err := os.MkdirAll(dir, 0o700); err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("create state dir: %v", err))
				return err
			}

			// Get binary path.
			exePath, err := os.Executable()
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("get executable path: %v", err))
				return err
			}

			// Install service unit.
			unit := service.Unit{
				Name:        "hl-agent",
				Description: "hl-agent hardware-locked provisioning agent",
				ExecPath:    exePath,
				ExecArgs:    []string{"run", "--dir", dir},
				User:        "",
			}

			err = tui.RunSpinner(os.Stdout, "installing service", func() error {
				return mgr.Install(unit)
			})
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("install service: %v", err))
				return err
			}

			// If server and token provided, run enrollment.
			if server != "" && token != "" {
				if hostname == "" {
					h, _ := os.Hostname()
					hostname = h
				}

				ks, err := keystore.OpenFile(dir)
				if err != nil {
					tui.Failure(os.Stderr, fmt.Sprintf("open keystore: %v", err))
					return err
				}

				var enrollResp *enrollment.EnrollResponse
				err = tui.RunSpinner(os.Stdout, "enrolling", func() error {
					r, err := enrollment.Run(ks, enrollment.EnrollOptions{
						Server:   server,
						Token:    token,
						Hostname: hostname,
					})
					enrollResp = r
					return err
				})
				if err != nil {
					tui.Failure(os.Stderr, fmt.Sprintf("enrollment failed: %v", err))
					return err
				}
				if enrollResp != nil {
					tui.KeyValue(os.Stdout, "host_id", enrollResp.HostID)
					tui.KeyValue(os.Stdout, "grpc_endpoint", enrollResp.GRPCEndpoint)
					tui.Info(os.Stdout, "agent will use the gRPC endpoint above for ongoing communication")
				}
			}

			// Start service.
			err = tui.RunSpinner(os.Stdout, "starting service", func() error {
				return mgr.Start("hl-agent")
			})
			if err != nil {
				tui.Failure(os.Stderr, fmt.Sprintf("start service: %v", err))
				return err
			}

			tui.Success(os.Stdout, "installation complete")
			return nil
		},
	}

	cmd.Flags().String("dir", resolveStateDir(), "state directory")
	cmd.Flags().String("server", "", "server enrollment URL (UI/API endpoint, e.g. https://hl.example.com); the gRPC endpoint is returned by the server")
	cmd.Flags().String("token", "", "one-time enrollment token from server admin")
	cmd.Flags().String("hostname", "", "agent hostname (default: os.Hostname)")
	cmd.Flags().Bool("unattended", false, "unattended mode (skip interactive wizard)")
	cmd.Flags().String("fetch", "", "fetch latest agent release from URL before installing (stub: not yet implemented)")

	return cmd
}
