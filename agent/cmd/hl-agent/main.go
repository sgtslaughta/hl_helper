// Package main provides the hl-agent command-line application.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/hlhelper/hl-agent/internal/decom"
	"github.com/hlhelper/hl-agent/internal/enrollment"
	xexec "github.com/hlhelper/hl-agent/internal/exec"
	"github.com/hlhelper/hl-agent/internal/executor"
	"github.com/hlhelper/hl-agent/internal/exposure"
	"github.com/hlhelper/hl-agent/internal/keystore"
	"github.com/hlhelper/hl-agent/internal/outbox"
	"github.com/hlhelper/hl-agent/internal/rotator"
	"github.com/hlhelper/hl-agent/internal/sleep"
	"github.com/hlhelper/hl-agent/internal/transport"
	"github.com/hlhelper/hl-agent/internal/updater"
	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
)

var (
	version = "dev"
	commit  = "none"
	date    = "unknown"
)

// Sync ldflag-injected version into the enrollment package so labels match
// heartbeats. Single source of truth: only main.version is overridden by
// the Makefile's -X ldflag.
func init() {
	enrollment.AgentVersion = version
}

// configPath holds the path to the agent configuration file, set via the --config flag.
var configPath string

// onFirstHealthyHeartbeat is called after the first successful heartbeat on a new binary.
// Used to confirm update health and clear the pending marker.
var onFirstHealthyHeartbeat func(string)

func bootCounterPath(dir string) string {
	return filepath.Join(dir, "bootcount")
}

func readBootCounter(dir string) int {
	b, err := os.ReadFile(bootCounterPath(dir))
	if err != nil {
		return 0
	}
	n, _ := strconv.Atoi(string(b))
	return n
}

func incrementBootCounter(dir string) {
	n := readBootCounter(dir) + 1
	_ = os.MkdirAll(dir, 0o755)
	_ = os.WriteFile(bootCounterPath(dir), []byte(strconv.Itoa(n)), 0o644)
}

func clearBootCounter(dir string) {
	_ = os.Remove(bootCounterPath(dir))
}

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
		newReenrollCmd(),
		runCmd(),
		decommissionCmd(),
		// Getters
		newGetHostIDCmd(),
		newGetEndpointCmd(),
		newGetConfigCmd(),
		newSetEndpointCmd(),
		newShowEndpointCmd(),
		// Info and lifecycle
		newInfoCmd(),
		newStartCmd(),
		newStopCmd(),
		newRestartCmd(),
		// Status, sleep, update
		newStatusCmd(),
		newSleepCmd(),
		newResumeCmd(),
		newUpdateCmd(),
		// Logs, doctor, install, uninstall
		newLogsCmd(),
		newDoctorCmd(),
		newInstallCmd(),
		newUninstallCmd(),
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
	enrollCmd := &cobra.Command{
		Use:   "enroll",
		Short: "enroll the agent",
		Long:  "enroll the agent with a server",
		RunE: func(cmd *cobra.Command, args []string) error {
			server, _ := cmd.Flags().GetString("server")
			token, _ := cmd.Flags().GetString("token")
			hostname, _ := cmd.Flags().GetString("hostname")
			dir, _ := cmd.Flags().GetString("dir")

			if hostname == "" {
				h, _ := os.Hostname()
				hostname = h
			}

			if err := os.MkdirAll(dir, 0700); err != nil {
				return fmt.Errorf("create keystore dir: %w", err)
			}

			ks, err := keystore.OpenFile(dir)
			if err != nil {
				return fmt.Errorf("open keystore: %w", err)
			}

			resp, err := enrollment.Run(ks, enrollment.EnrollOptions{
				Server:   server,
				Token:    token,
				Hostname: hostname,
			})
			if err != nil {
				return err
			}

			// Reset result chain state so a fresh enrollment starts at the
			// genesis anchor and is not rejected by the server's chain check
			// against stale prev_hash from a prior enrollment.
			for _, name := range []string{"result.seq", "result.prev_hash"} {
				p := filepath.Join(dir, name)
				if err := os.Remove(p); err != nil && !os.IsNotExist(err) {
					fmt.Fprintf(cmd.ErrOrStderr(), "warn: clear %s: %v\n", name, err)
				}
			}

			fmt.Fprintf(cmd.OutOrStdout(), "enrolled: host_id=%s\n", resp.HostID)
			return nil
		},
	}

	enrollCmd.Flags().String("server", "", "server URL (required)")
	enrollCmd.Flags().String("token", "", "enrollment token (required)")
	enrollCmd.Flags().String("hostname", "", "agent hostname (default: os.Hostname)")
	enrollCmd.Flags().String("dir", "/var/lib/hl-agent", "keystore directory")
	enrollCmd.MarkFlagRequired("server")
	enrollCmd.MarkFlagRequired("token")

	return enrollCmd
}

func runCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "run",
		Short: "run the agent (connect to server and stream commands)",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")

			// Load enrollment manifest for grpc_endpoint.
			mfBytes, err := os.ReadFile(filepath.Join(dir, "manifest.json"))
			if err != nil {
				return fmt.Errorf("read manifest (run hl-agent enroll first): %w", err)
			}
			var manifest map[string]string
			if err := json.Unmarshal(mfBytes, &manifest); err != nil {
				return fmt.Errorf("parse manifest: %w", err)
			}
			endpoint := manifest["grpc_endpoint"]
			if endpoint == "" {
				return fmt.Errorf("manifest missing grpc_endpoint")
			}
			hostID := manifest["host_id"]
			if hostID == "" {
				return fmt.Errorf("manifest missing host_id")
			}

			ks, err := keystore.OpenFile(dir)
			if err != nil {
				return fmt.Errorf("open keystore: %w", err)
			}

			// Handle pending updates: check boot counter and potentially rollback
			stateDir := os.Getenv("HL_STATE_DIR")
			if stateDir == "" {
				stateDir = "/var/lib/hl-agent"
			}
			updaterDir := filepath.Join(stateDir, "updates")
			installPath, err := os.Executable()
			if err != nil {
				return fmt.Errorf("get executable path: %w", err)
			}

			_, _, pending := updater.ReadPending(updaterDir)
			if pending {
				bootCount := readBootCounter(updaterDir)
				if bootCount >= 2 {
					// Too many boot attempts, rollback
					handler := updater.Handler{StateDir: updaterDir, InstallPath: installPath}
					if err := handler.Rollback(); err != nil {
						fmt.Fprintf(cmd.ErrOrStderr(), "warn: rollback failed: %v\n", err)
					}
					clearBootCounter(updaterDir)
					// Relaunch with current binary to avoid re-executing new binary
					_ = updater.SyscallRelaunch(installPath, os.Args, os.Environ())
					return fmt.Errorf("relaunch after rollback failed")
				}
				// Increment boot counter and set up first-healthy callback
				incrementBootCounter(updaterDir)
				onFirstHealthyHeartbeat = func(ver string) {
					handler := updater.Handler{StateDir: updaterDir, InstallPath: installPath}
					if err := handler.ConfirmHealthy(ver); err != nil {
						fmt.Fprintf(cmd.ErrOrStderr(), "warn: confirm healthy failed: %v\n", err)
					}
					clearBootCounter(updaterDir)
				}
			}

			ob, err := outbox.OpenWithKeyFile(
				filepath.Join(dir, "outbox.db"),
				filepath.Join(dir, "outbox.key"),
				outbox.Options{
					MaxEntries: 10_000,
					MaxBytes:   64 * 1024 * 1024,
				},
			)
			if err != nil {
				return fmt.Errorf("open outbox: %w", err)
			}
			defer ob.Close()

			elev := xexec.DetectElevator()
			log.Printf("elevator: kind=%s path=%s", elev.Kind, elev.Path)
			auditCh := make(chan *pb.AgentToServer, 32)
			sink := executor.NewMultiSink(
				executor.NewJSONLSink("/var/log/hl-agent/elevated.jsonl", 10*1024*1024),
				executor.NewBridgeSink(auditCh),
			)

			client := transport.New(transport.Options{
				Endpoint:     endpoint,
				HostID:       hostID,
				Keystore:     ks,
				Outbox:       ob,
				Executor:     &ShellExecutor{StateDir: stateDir, Elevator: elev, Sink: sink},
				Signer:       ks,
				KeystoreDir:  dir,
				AgentVersion: version,
				StateDir:     stateDir,
				AuditChan:    auditCh,
				OnCommand: func(env *pb.CommandEnvelope) {
					fmt.Fprintf(cmd.OutOrStdout(), "command received: id=%s\n", env.GetCommandId())
				},
			})

			// Set the first-healthy callback if a pending update was detected
			if onFirstHealthyHeartbeat != nil {
				client.SetFirstHealthyCallback(onFirstHealthyHeartbeat)
			}

			ctx, cancel := signal.NotifyContext(
				context.Background(), os.Interrupt, syscall.SIGTERM,
			)
			defer cancel()

			fmt.Fprintf(cmd.OutOrStdout(), "hl-agent connecting to %s\n", endpoint)

			// Start transport client in background
			transportDone := make(chan error, 1)
			go func() {
				transportDone <- client.Run(ctx)
			}()

			// Build rotator transport adapter
			rotatorTransport := &rotatorTransportAdapter{client: client}
			ksAdapter := &rotatorKeystoreAdapter{Keystore: ks}

			// Build rotator
			rot := rotator.New(rotator.Config{
				HostID:       hostID,
				Transport:    rotatorTransport,
				Keystore:     ksAdapter,
				StatePath:    filepath.Join(stateDir, "rotator.state.json"),
				PrevSerialFn: func() (string, error) {
					_, _, serial, err := certInfoFromKeystore(ks)()
					return serial, err
				},
			})

			// Build recovery with reenroll client
			rootCAPEM, _ := ks.RootCAPEM()
			reenrollEndpoint := os.Getenv("HL_REENROLL_ENDPOINT")
			if reenrollEndpoint == "" {
				log.Printf("warn: HL_REENROLL_ENDPOINT not set, recovery disabled")
				reenrollEndpoint = "unknown:7444"
			}

			reenrollSrv := &enrollment.GRPCReenrollServer{
				Endpoint:  reenrollEndpoint,
				RootCAPEM: rootCAPEM,
			}
			reenrollClient := &enrollment.ReenrollClient{
				HostID:   hostID,
				Keystore: &reenrollKSAdapter{keystore: ks},
				Server:   reenrollSrv,
			}
			rec := rotator.NewRecovery(rotator.RecoveryConfig{
				StatePath:  filepath.Join(stateDir, "rotator.state.json"),
				CertInfoFn: certInfoFromKeystore(ks),
				ReEnroller: reenrollClient,
				Keystore:   ksAdapter,
				Transport:  rotatorTransport,
			})

			// Start rotator (long-running)
			go func() {
				if err := rot.Run(ctx, certInfoFromKeystore(ks)); err != nil {
					log.Printf("rotator: %v", err)
				}
			}()

			// Start recovery supervisor (periodic check)
			go func() {
				t := time.NewTicker(60 * time.Second)
				defer t.Stop()
				for {
					select {
					case <-ctx.Done():
						return
					case <-t.C:
						if err := rec.CheckAndRecover(ctx); err != nil {
							log.Printf("recovery: %v", err)
						}
					}
				}
			}()

			// Listen for server-pushed RunCertRotate
			go func() {
				for {
					select {
					case <-ctx.Done():
						return
					case <-client.RunCertRotateCh():
						if err := rot.RotateOnce(ctx); err != nil {
							log.Printf("rotator (forced): %v", err)
						}
					}
				}
			}()

			// Build exposure scanner
			scanner := &exposure.Scanner{
				HostID:     hostID,
				Timeout:    60 * time.Second,
				Resolver:   exposure.NewCachedResolver(exposure.AutoResolver()),
				Collectors: []exposure.Collector{
					&exposure.ProcessCollector{},
					&exposure.SocketCollector{},
					&exposure.SystemdServiceCollector{},
					&exposure.KmodCollector{},
					&exposure.ContainerCollector{},
				},
			}

			doScan := func() {
				sctx, cancel := context.WithTimeout(ctx, 90*time.Second)
				defer cancel()
				exp := scanner.Scan(sctx)
				if err := client.SendRuntimeExposure(sctx, exp); err != nil {
					log.Printf("exposure scan send: %v", err)
				} else {
					log.Printf("exposure scan sent host=%s procs=%d listeners=%d truncated=%v",
						hostID, len(exp.Processes), len(exp.Listeners), exp.Truncated)
				}
			}

			// Long-running scan loop: every exposureInterval (default 6h)
			go func() {
				exposureInterval := 6 * time.Hour
				if v := os.Getenv("HL_EXPOSURE_INTERVAL_HOURS"); v != "" {
					if n, err := strconv.Atoi(v); err == nil && n > 0 {
						exposureInterval = time.Duration(n) * time.Hour
					}
				}
				t := time.NewTicker(exposureInterval)
				defer t.Stop()

				// First scan ~30s after boot to give transport time to settle.
				select {
				case <-time.After(30 * time.Second):
					doScan()
				case <-ctx.Done():
					return
				}

				for {
					select {
					case <-ctx.Done():
						return
					case <-t.C:
						doScan()
					case req := <-client.RunExposureScanCh():
						log.Printf("exposure scan triggered (reason=%s)", req.Reason)
						doScan()
					}
				}
			}()

			return <-transportDone
		},
	}
	cmd.Flags().String("dir", "/var/lib/hl-agent", "keystore directory")
	return cmd
}

func decommissionCmd() *cobra.Command {
	decommissionCmd := &cobra.Command{
		Use:   "decommission",
		Short: "decommission the agent",
		Long:  "decommission the agent, securely wiping all sensitive data",
		RunE: func(cmd *cobra.Command, args []string) error {
			dir, _ := cmd.Flags().GetString("dir")
			force, _ := cmd.Flags().GetBool("force")

			if !force {
				fmt.Fprintf(cmd.OutOrStderr(), "decommission will wipe %s — pass --force to proceed\n", dir)
				return fmt.Errorf("not forced")
			}

			return decom.Run(decom.Options{Dir: dir, Force: force, Overwrite: 1})
		},
	}

	decommissionCmd.Flags().String("dir", "/var/lib/hl-agent", "keystore directory")
	decommissionCmd.Flags().Bool("force", false, "confirm decommissioning")

	return decommissionCmd
}

// ShellExecutor implements transport.Executor using RunShell.
type ShellExecutor struct {
	StateDir string
	Elevator xexec.Elevator
	Sink     executor.AuditSink
}

func (e *ShellExecutor) Execute(ctx context.Context, cmd *pb.CommandEnvelope) *pb.ResultEnvelope {
	// Extract ShellExec payload
	shellExec := cmd.GetShellExec()
	if shellExec == nil {
		return &pb.ResultEnvelope{
			StartedAt:       timestamppb.Now(),
			CompletedAt:     timestamppb.Now(),
			Status:          pb.ResultStatus_RESULT_REJECTED,
			RejectionReason: "not a shell_exec command",
		}
	}

	// Check if agent is sleeping
	sleeping, sleepUntil := sleep.Check(e.StateDir)
	if sleeping {
		return &pb.ResultEnvelope{
			StartedAt:       timestamppb.Now(),
			CompletedAt:     timestamppb.Now(),
			ExitCode:        124, // timeout-like exit code
			StderrChunk:     []byte(fmt.Sprintf("agent sleeping until %s", sleepUntil.Format(time.RFC3339))),
			Status:          pb.ResultStatus_RESULT_FAIL,
			RejectionReason: "agent sleeping",
		}
	}

	// Extract timeout from the command
	timeoutSec := int(shellExec.TimeoutSeconds)
	if timeoutSec <= 0 {
		timeoutSec = 30
	}

	// Create a timeout context
	ctx, cancel := context.WithTimeout(ctx, time.Duration(timeoutSec)*time.Second)
	defer cancel()

	// Run the shell command
	cmdStr := shellExec.Command
	var stdout, stderr []byte
	var exitCode int32
	var status pb.ResultStatus

	if shellExec.AsRoot {
		stdout, stderr, exitCode, status = executor.RunShellElevated(ctx, cmdStr, timeoutSec, executor.ElevatedRequest{
			Elevator: e.Elevator,
			TaskID:   cmd.CommandId,
			Reason:   shellExec.Reason,
			Sink:     e.Sink,
		})
	} else {
		stdout, stderr, exitCode, status = executor.RunShell(ctx, cmdStr, timeoutSec)
	}

	// Build the result envelope
	result := &pb.ResultEnvelope{
		StartedAt:   timestamppb.Now(),
		CompletedAt: timestamppb.Now(),
		ExitCode:    exitCode,
		StdoutChunk: stdout,
		StderrChunk: stderr,
		Status:      status,
	}

	return result
}
