---
title: Agent Installation
status: stable
---

# Agent Installation

Install the hl_helper agent on Linux/Unix hosts. The agent is a single static binary with minimal dependencies.

---

## Quick Start (All Distros)

```bash
# Download and install as unprivileged user with sudoers access
curl -fsSL https://fleet.example.com/install.sh | sudo bash

# Then enroll with bootstrap token
sudo hl-agent enroll --server https://fleet.example.com:50051 --token hlb_xxx
```

**TBD**: Verify `/install.sh` script URL and behavior. Confirm it handles all distros and installation paths.

---

## Per-Distro Installation

### Debian / Ubuntu (apt)

```bash
# Add repo (if available; TBD — confirm repo setup)
curl https://fleet.example.com/apt-key.gpg | sudo apt-key add -
echo "deb [signed-by=/usr/share/keyrings/hl-helper.gpg] https://fleet.example.com/apt jammy main" | \
  sudo tee /etc/apt/sources.list.d/hl-helper.list

# Install
sudo apt update
sudo apt install -y hl-agent

# Enable and start
sudo systemctl enable hl-agent
sudo systemctl start hl-agent
```

Or, install `.deb` directly:

```bash
curl -o /tmp/hl-agent.deb https://fleet.example.com/releases/hl-agent_0.1.0_amd64.deb
sudo dpkg -i /tmp/hl-agent.deb
sudo systemctl start hl-agent
```

### RHEL / Fedora / AlmaLinux (dnf/yum)

```bash
# Add repo (TBD)
sudo dnf config-manager --add-repo https://fleet.example.com/hl-agent.repo

# Install
sudo dnf install -y hl-agent

# Enable and start
sudo systemctl enable hl-agent
sudo systemctl start hl-agent
```

Or, install `.rpm` directly:

```bash
curl -o /tmp/hl-agent.rpm https://fleet.example.com/releases/hl-agent-0.1.0-1.x86_64.rpm
sudo dnf install -y /tmp/hl-agent.rpm
sudo systemctl start hl-agent
```

### Alpine Linux (apk)

```bash
# Add repo (TBD)
echo "https://fleet.example.com/apk" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add hl-agent

# Enable and start
sudo rc-service hl-agent start
```

Or, for OpenRC with default runlevel:

```bash
sudo rc-update add hl-agent
```

### Arch / Manjaro (pacman)

```bash
# Option 1: AUR (if packaged; TBD)
yay -S hl-agent

# Option 2: Tarball + systemd unit
curl -o /tmp/hl-agent.tar.gz https://fleet.example.com/releases/hl-agent_0.1.0_linux_amd64.tar.gz
sudo tar -xzf /tmp/hl-agent.tar.gz -C /usr/local/bin/

# Install systemd unit
sudo tee /etc/systemd/system/hl-agent.service > /dev/null <<'EOF'
[Unit]
Description=HL Helper Agent
After=network.target

[Service]
Type=simple
User=hl-agent
Group=hl-agent
ExecStart=/usr/local/bin/hl-agent daemon
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hl-agent
sudo systemctl start hl-agent
```

### Generic Tarball (Any Distro)

```bash
# Download
curl -o /tmp/hl-agent.tar.gz https://fleet.example.com/releases/hl-agent_0.1.0_linux_amd64.tar.gz

# Extract to /usr/local/bin (or /opt/hl-agent)
sudo tar -xzf /tmp/hl-agent.tar.gz -C /usr/local/bin/

# Verify
sudo /usr/local/bin/hl-agent --version
# hl-agent version 0.1.0, build abc123...

# Create unprivileged user (if not exists)
sudo useradd -r -s /usr/sbin/nologin hl-agent 2>/dev/null || true

# Install systemd unit (see below)
# Install sudoers fragment (see below)

# Start service
sudo systemctl enable hl-agent
sudo systemctl start hl-agent
```

---

## Required User & Permissions

The agent runs as an unprivileged user (`hl-agent`) and uses `sudo` for privileged operations only (package manager, reboot, container daemon access).

### Create unprivileged user

```bash
sudo useradd -r -s /usr/sbin/nologin -d /var/lib/hl-agent -m hl-agent 2>/dev/null || true
```

### Sudoers fragment

Create `/etc/sudoers.d/hl-agent`:

```sudoers
# HL Helper Agent
# Minimal privileged operations for package management and system control

Defaults:hl-agent !requiretty, !use_pty, log_output

hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt, /usr/bin/dpkg, \
                            /usr/bin/dnf, /usr/bin/yum, /usr/bin/rpm, \
                            /usr/bin/pacman, /usr/bin/apk, \
                            /usr/bin/systemctl, /usr/sbin/reboot, /usr/sbin/poweroff, /usr/sbin/shutdown, \
                            /usr/bin/docker, /usr/bin/podman, /run/docker.sock, \
                            /usr/bin/mount, /usr/bin/umount, /usr/sbin/fsck, \
                            /usr/bin/find, /usr/bin/getfacl, /usr/bin/lsblk, \
                            /bin/systemctl, /sbin/reboot, /sbin/poweroff, /sbin/shutdown

# Deny shell access (prevent privilege escalation)
hl-agent ALL = NOPASSWD: /usr/bin/false
```

**Important**: Use `visudo` to validate syntax:

```bash
sudo visudo -c -f /etc/sudoers.d/hl-agent
# parse error in /etc/sudoers.d/hl-agent near line N
# (or "syntax OK" if valid)
```

### Set permissions

```bash
sudo chmod 0440 /etc/sudoers.d/hl-agent
sudo chown root:root /etc/sudoers.d/hl-agent
```

### Capability bounds (hardening)

To further restrict the agent, use Linux capabilities:

```bash
sudo setcap cap_sys_admin+ep /usr/local/bin/hl-agent
```

This allows only privileged operations without full `CAP_SYS_ADMIN`. **TBD**: Confirm exact capabilities needed.

---

## Systemd Unit

If not provided by package manager, create `/etc/systemd/system/hl-agent.service`:

```ini
[Unit]
Description=HL Helper Agent
Documentation=https://docs.hl-helper.local/admin/deployment/agent-install
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hl-agent
Group=hl-agent
WorkingDirectory=/var/lib/hl-agent

# Graceful shutdown (SIGTERM → 30s wait → SIGKILL)
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

# Restarts
Restart=on-failure
RestartSec=10
StartLimitInterval=5m
StartLimitBurst=3

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/hl-agent /var/log/hl-agent
DevicePolicy=closed

# Resource limits
MemoryLimit=512M
CPUQuota=50%
TasksMax=100

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hl-agent

# Service binary
ExecStart=/usr/local/bin/hl-agent daemon \
  --config-dir=/var/lib/hl-agent \
  --log-level=info

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable hl-agent
sudo systemctl start hl-agent
sudo systemctl status hl-agent
```

---

## Verify Installation

### Check service status

```bash
sudo systemctl status hl-agent
# ● hl-agent.service - HL Helper Agent
#   Loaded: loaded (/etc/systemd/system/hl-agent.service; enabled; ...)
#   Active: active (running) since 2026-05-09 14:30:30 UTC; 30s ago
```

### Check logs

```bash
sudo journalctl -u hl-agent -n 20 --no-pager
# [INFO] Agent started (version 0.1.0)
# [INFO] Loaded config from /var/lib/hl-agent/config.json
# [INFO] Reading certificate from /var/lib/hl-agent/tls.crt
```

### Health check

```bash
sudo hl-agent health
# Status: not_enrolled (waiting for enrollment)
```

After enrollment:

```bash
sudo hl-agent status
# Host ID: host_a1b2c3d4e5f6g7h8
# Status: connected (5 minutes uptime)
# Cert expires: 2026-05-16 14:30:00 UTC (7 days)
# Last heartbeat: 2026-05-09 14:35:42 UTC
```

---

## Data Directory Layout

The agent stores keys, certificates, and cache in `/var/lib/hl-agent/`:

```
/var/lib/hl-agent/
├── tls.crt            # Current TLS certificate (7-day TTL)
├── tls.key            # TLS private key (never leave disk unencrypted)
├── tls.crt.prev       # Previous cert (for rollback on rotation failure)
├── ca_root.pem        # Pinned server root CA (for TLS verification)
├── signing.key        # Agent Ed25519 signing key (lifetime of agent)
├── manifest.json      # Latest capability manifest from server
├── outbox.db          # BoltDB: queued commands, results awaiting ACK
├── config.json        # Agent config (server URL, log level, etc.)
└── logs/
    └── agent.log      # Rotated logs (if enabled)
```

**Permissions**:
- Owner: `hl-agent` user, `hl-agent` group
- Directory: `0700` (read/write/execute for owner only)
- Files: `0600` (read/write for owner only)

---

## Configuration

Agent reads config from `/var/lib/hl-agent/config.json` or environment variables:

```json
{
  "server_url": "https://fleet.example.com:50051",
  "log_level": "info",
  "heartbeat_interval": 30,
  "max_concurrent_commands": 3,
  "capability_manifest_ttl": 3600,
  "tls_cert_path": "/var/lib/hl-agent/tls.crt",
  "tls_key_path": "/var/lib/hl-agent/tls.key",
  "ca_path": "/var/lib/hl-agent/ca_root.pem"
}
```

Or via environment:

```bash
export FLEET_SERVER_URL="https://fleet.example.com:50051"
export FLEET_LOG_LEVEL="debug"
export FLEET_HEARTBEAT_INTERVAL=60
sudo systemctl restart hl-agent
```

---

## Upgrade Agent

When a new agent version is available, administrators can push an upgrade command:

```bash
# Admin: trigger upgrade on all hosts
curl -X POST http://localhost:8000/v1/commands \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "system.upgrade_agent",
    "targets": ["all"],
    "parameters": {
      "version": "0.2.0",
      "skip_verify": false
    }
  }'
```

On each agent:

1. Download new binary
2. Verify signature (cosign, or internal CA)
3. Stage to temp location
4. Graceful restart (finish in-flight commands, then exec new binary)
5. Confirm new version running

Automatic rollback if heartbeat fails after 60 seconds.

---

## Troubleshooting

### Agent won't start: "permission denied"

**Symptom**: `systemctl status hl-agent` shows `code=exited, status=1`

**Causes**:
- Binary missing or not executable
- Config directory not readable
- TLS cert not readable

**Fix**:
```bash
# Check binary
sudo ls -l /usr/local/bin/hl-agent
# should be executable: -rwxr-xr-x

# Check permissions
sudo ls -ld /var/lib/hl-agent
# should be: drwx------ hl-agent:hl-agent

# Check logs
sudo journalctl -u hl-agent -n 50 --no-pager | grep -i "error"
```

### Cannot enroll: "permission denied accessing /var/lib/hl-agent"

**Cause**: `/var/lib/hl-agent` not writable by `hl-agent` user

**Fix**:
```bash
sudo chown -R hl-agent:hl-agent /var/lib/hl-agent
sudo chmod -R u=rwX,go= /var/lib/hl-agent
```

### Sudoers errors after enrollment

**Symptom**: Package updates fail with `sudo: no password was provided, but a password is required`

**Cause**: Sudoers fragment not installed or has syntax error

**Fix**:
```bash
# Verify sudoers file
sudo visudo -c -f /etc/sudoers.d/hl-agent

# Reinstall if broken
sudo rm /etc/sudoers.d/hl-agent
# (re-create from Agent Installation section)
sudo chmod 0440 /etc/sudoers.d/hl-agent

# Test
sudo -u hl-agent -n apt-get --help >/dev/null 2>&1 && echo "sudoers OK" || echo "sudoers broken"
```

### Agent repeatedly crashes and restarts

**Symptom**: `systemctl status hl-agent` shows frequent restarts

**Cause**: Likely an outbox corruption or config issue

**Fix**:
```bash
# Check logs for panic
sudo journalctl -u hl-agent --no-pager | grep -i "panic\|fatal"

# Wipe outbox (safe; commands will be re-fetched)
sudo rm /var/lib/hl-agent/outbox.db

# Restart
sudo systemctl restart hl-agent

# Monitor
sudo journalctl -u hl-agent -f
```

### TLS certificate expired (before rotation triggered)

**Symptom**: Agent cannot connect; logs show `certificate has expired`

**Cause**: Rotation logic failed to trigger (unlikely unless system clock is far off)

**Fix**:
```bash
# Manually trigger cert rotation
sudo hl-agent rotate-cert

# Or, re-enroll with new token (nuclear option)
sudo rm /var/lib/hl-agent/tls.* /var/lib/hl-agent/ca_root.pem
sudo systemctl restart hl-agent
# (then enroll again with new bootstrap token)
```

---

## Security Notes

- **Keys on disk**: TLS and signing keys are stored unencrypted (`0600`). Ensure `/var/lib/hl-agent` is on an encrypted filesystem.
- **Systemd hardening**: The unit above uses `ProtectSystem=strict`, limiting write access. Adjust `ReadWritePaths` if agent needs to write elsewhere.
- **Sudo elevation**: Agent can run privileged commands via sudo. Review sudoers fragment regularly for scope creep.
- **Capability manifest**: Server delivers a signed manifest declaring which commands are allowed per host. Agent enforces this; a compromised server cannot trick an agent into running unintended commands.

---

## References

- [Enrollment](./enroll-host.md) — Zero-trust onboarding
- [Key Rotation](../../developer/design/key-rotation.md) — Cert lifecycle
- [Agent Privilege Model](../../developer/secure-dev/agent-privilege-model.md) — Security & sudo usage
- [Recovery Procedures](../runbooks/recovery.md) — Incident response
