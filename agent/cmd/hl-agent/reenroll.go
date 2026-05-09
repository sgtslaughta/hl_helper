package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/spf13/cobra"

	"github.com/hlhelper/hl-agent/internal/enrollment"
	"github.com/hlhelper/hl-agent/internal/keystore"
)

func newReenrollCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "reenroll",
		Short: "Re-enroll this host using a token (operator-issued recovery flow)",
		RunE: func(cmd *cobra.Command, args []string) error {
			url, _ := cmd.Flags().GetString("url")
			token, _ := cmd.Flags().GetString("token")
			dir, _ := cmd.Flags().GetString("dir")

			if url == "" || token == "" {
				return fmt.Errorf("--url and --token required")
			}

			ctx, cancel := context.WithTimeout(cmd.Context(), 60*time.Second)
			defer cancel()
			return runReenrollViaToken(ctx, url, token, dir)
		},
	}
	cmd.Flags().String("url", "", "reenroll endpoint URL")
	cmd.Flags().String("token", "", "re-enrollment token (hlb_...)")
	cmd.Flags().String("dir", "/var/lib/hl-agent", "keystore directory")
	return cmd
}

func runReenrollViaToken(ctx context.Context, url, token, dir string) error {
	ks, err := keystore.OpenFile(dir)
	if err != nil {
		return fmt.Errorf("open keystore: %w", err)
	}

	resp, err := enrollment.Run(ks, enrollment.EnrollOptions{
		Server:   url,
		Token:    token,
		Hostname: "unknown",
	})
	if err != nil {
		return fmt.Errorf("reenroll: %w", err)
	}

	// Reset result chain state so a fresh reenrollment starts at genesis.
	for _, name := range []string{"result.seq", "result.prev_hash"} {
		p := filepath.Join(dir, name)
		if err := os.Remove(p); err != nil && !os.IsNotExist(err) {
			fmt.Fprintf(os.Stderr, "warn: clear %s: %v\n", name, err)
		}
	}

	fmt.Fprintf(os.Stdout, "re-enrollment complete: host_id=%s\n", resp.HostID)
	return nil
}
