# Agent Privilege Model

This document describes how the hl_helper agent enforces the principle of least privilege on each host.

## Quick overview

The agent runs as an unprivileged system user (`hl-agent:hl-agent`) with a minimal sudoers allowlist and systemd hardening. Even if compromised, it cannot escalate beyond its sudoers grants or read sensitive system files. Commands are signed by the server and verified by the agent before execution. All executions are logged to the audit chain.

---

## Linux user and group

The agent runs as a dedicated, unprivileged system user created during install:

```bash
# Created at install time
sudo useradd -r -s /usr/sbin/nologin -d /var/lib/hl-agent -m hl-agent
```

- **User**: `hl-agent`
- **Group**: `hl-agent`
- **Home**: `/var/lib/hl-agent`
- **Shell**: `/usr/sbin/nologin` (no login)
- **UID/GID**: system-assigned (typically < 1000 on Debian-based systems)

This ensures the agent:
- Cannot read `/etc/shadow` or other sensitive files
- Cannot modify system configuration files
- Cannot elevate to root without explicit sudo allowlist

---

## Sudoers allowlist by distribution

Each supported distribution has a per-distro sudoers fragment that whitelists only the binaries and arguments the agent is allowed to execute via `sudo`. All entries use `NOPASSWD` (agent does not prompt for a password).

### Debian / Ubuntu

File: `deploy/agent/sudoers.d/hl-agent.deb`

```
# hl_helper agent sudoers allowlist — Debian/Ubuntu
# All entries are NOPASSWD and path-pinned.

Defaults:hl-agent !requiretty
Defaults:hl-agent secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get update
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get install *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get remove *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get autoremove *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get upgrade *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get dist-upgrade *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get full-upgrade *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl enable *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl disable *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl start *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl stop *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl restart *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl reload *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl is-active *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl is-enabled *
hl-agent ALL=(ALL) NOPASSWD: /sbin/reboot
hl-agent ALL=(ALL) NOPASSWD: /sbin/shutdown -h *
hl-agent ALL=(ALL) NOPASSWD: /sbin/poweroff
hl-agent ALL=(ALL) NOPASSWD: /usr/sbin/needrestart *
hl-agent ALL=(ALL) NOPASSWD: /snap/bin/snap install *
hl-agent ALL=(ALL) NOPASSWD: /snap/bin/snap refresh *
hl-agent ALL=(ALL) NOPASSWD: /snap/bin/snap remove *
hl-agent ALL=(ALL) NOPASSWD: /snap/bin/snap revert *
```

**Validated**: `visudo -c -f /etc/sudoers.d/hl-agent.deb` (run during install).

### Rocky / Fedora / RHEL

File: `deploy/agent/sudoers.d/hl-agent.rpm`

```
Defaults:hl-agent !requiretty
Defaults:hl-agent secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

hl-agent ALL=(ALL) NOPASSWD: /usr/bin/dnf install *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/dnf remove *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/dnf update *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/dnf upgrade *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/dnf autoremove *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl enable *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl disable *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl start *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl stop *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl restart *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl reload *
hl-agent ALL=(ALL) NOPASSWD: /sbin/reboot
hl-agent ALL=(ALL) NOPASSWD: /sbin/shutdown -h *
hl-agent ALL=(ALL) NOPASSWD: /sbin/poweroff
```

### Arch Linux

File: `deploy/agent/sudoers.d/hl-agent.arch`

```
Defaults:hl-agent !requiretty
Defaults:hl-agent secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

hl-agent ALL=(ALL) NOPASSWD: /usr/bin/pacman -S *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/pacman -R *
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/pacman -Syu
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/pacman -Su
hl-agent ALL=(ALL) NOPASSWD: /usr/bin/pacman -Sy
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl enable *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl disable *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl start *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl stop *
hl-agent ALL=(ALL) NOPASSWD: /bin/systemctl restart *
hl-agent ALL=(ALL) NOPASSWD: /sbin/reboot
hl-agent ALL=(ALL) NOPASSWD: /sbin/shutdown -h *
```

### Alpine Linux

File: `deploy/agent/sudoers.d/hl-agent.alpine`

```
Defaults:hl-agent !requiretty
Defaults:hl-agent secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

hl-agent ALL=(ALL) NOPASSWD: /sbin/apk add *
hl-agent ALL=(ALL) NOPASSWD: /sbin/apk del *
hl-agent ALL=(ALL) NOPASSWD: /sbin/apk upgrade *
hl-agent ALL=(ALL) NOPASSWD: /bin/kill *
hl-agent ALL=(ALL) NOPASSWD: /sbin/reboot
hl-agent ALL=(ALL) NOPASSWD: /sbin/halt -p
hl-agent ALL=(ALL) NOPASSWD: /sbin/poweroff
```

---

## Systemd hardening

The agent is installed as a systemd service with extensive security hardening. All directives are locked in the service unit.

File: `deploy/agent/systemd/hl-agent.service`

```ini
[Unit]
Description=hl_helper Agent
Documentation=https://docs.hl-helper.local/agent
After=network-online.target
Wants=network-online.target

[Service]
# Run as unprivileged user
User=hl-agent
Group=hl-agent

# Type and socket
Type=simple
ExecStart=/usr/local/bin/hl-agent service

# Environment and working directory
Environment="HL_AGENT_CONFIG=/var/lib/hl-agent/config.json"
WorkingDirectory=/var/lib/hl-agent

# Hardening: prevent privilege escalation
NoNewPrivileges=yes

# Hardening: restrict filesystem access
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
PrivateTmp=yes
PrivateDevices=yes
PrivateNetwork=no  # needs network for gRPC
ReadWritePaths=/var/lib/hl-agent

# Hardening: drop all capabilities
CapabilityBoundingSet=

# Hardening: restrict system calls
SystemCallFilter=@system-service
SystemCallFilter=~@privileged @resources

# Hardening: restrict realtime + CPU affinity
RestrictRealtime=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

# Hardening: immutable binaries
ProtectSystem=strict
ProtectClock=yes
SystemCallArchitectures=native

# Restart policy
Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=60

[Install]
WantedBy=multi-user.target
```

Key hardening points:
- `NoNewPrivileges=yes` — cannot gain new privileges via suid/sgid binaries
- `ProtectSystem=strict` — filesystem is read-only except `/var/lib/hl-agent`
- `PrivateTmp=yes` — isolated `/tmp`
- `CapabilityBoundingSet=` — **empty** — no Linux capabilities at all
- `SystemCallFilter` — restrict to safe syscalls only
- `RestrictAddressFamilies` — IPv4/IPv6/Unix sockets only (no netlink, etc.)

---

## Capability manifest

At enrollment, the server issues a per-host **capability manifest** — a signed JSON document that declares which command types the agent will accept.

File location: `/var/lib/hl-agent/manifest.json`

Example:

```json
{
  "host_id": "spiffe://fleet/host/abcd-1234",
  "issued_at": "2026-05-02T10:00:00Z",
  "expires_at": "2026-05-09T10:00:00Z",
  "signature": "<Ed25519 base64>",
  "allowed_actions": [
    "pkg_update",
    "get_facts",
    "reboot",
    "systemctl_control"
  ],
  "max_risk_level": "HIGH",
  "config": {
    "pkg_update": {
      "classes": ["security", "bugfix"],
      "allow_major_version_jumps": false
    },
    "reboot": {
      "requires_approval": true,
      "max_delay_seconds": 300
    },
    "shell_exec": {
      "denied": "this_host_blocks_shell_exec"
    }
  }
}
```

**Enforcement**: Agent verifies manifest signature before accepting any command. Commands referencing an action outside the manifest receive a `CAPABILITY_DENIED` result.

---

## What the agent CAN do

- **Receive signed commands** over mTLS gRPC
- **Execute approved commands** from sudoers allowlist (e.g., `apt-get install`, `systemctl restart`)
- **Return signed results** to the server
- **Report heartbeats** and metrics
- **Renew TLS certificates** at 50% TTL
- **Request capability tokens** for specific operations (biscuit-attenuated)
- **Rotate its Ed25519 signing key** (server-initiated)
- **Self-decommission** via `hl-agent decommission --force` (wipes keys + outbox)

---

## What the agent CANNOT do

- **Read `/etc/shadow`** — no sudo grants, no capability
- **Mutate sudoers** — sudoers is root-owned; agent cannot write to `/etc/sudoers.d/`
- **Install arbitrary packages** — sudoers allows only *specific* package managers with *specific* args
- **Talk to other hosts** — outbound-only to server's gRPC endpoint; no arbitrary network
- **Mutate server state** — gRPC API restricted to read-only + heartbeat + result submission
- **Escalate beyond sudoers allowlist** — if sudoers says no `/bin/rm`, agent can never execute it
- **Modify its manifest** — manifest is signed by server; agent cannot reissue it
- **Access other agents' keys** — each agent holds only its own signing + TLS keys
- **Override approval gates** — high-risk commands require admin approval regardless of manifest

---

## Third-party packages (snap, flatpak, homebrew)

Commands like `snap install` are run as the `hl-agent` user (no sudo):

```bash
sudo -u hl-agent snap install <package>
```

This means:
- Snaps are installed to the hl-agent user's scope, not system-wide
- Same privilege isolation applies (cannot escalate beyond hl-agent's own capabilities)
- Flatpak operates in user-mode sandboxed environment

---

## File permissions

| Path | Owner | Mode | Notes |
|---|---|---|---|
| `/usr/local/bin/hl-agent` | root | 0755 | agent binary, world-readable |
| `/var/lib/hl-agent/` | hl-agent:hl-agent | 0700 | agent home directory |
| `/var/lib/hl-agent/signing.key` | hl-agent:hl-agent | 0600 | agent signing private key (or TPM-sealed) |
| `/var/lib/hl-agent/tls.key` | hl-agent:hl-agent | 0600 | agent TLS private key |
| `/var/lib/hl-agent/manifest.json` | hl-agent:hl-agent | 0600 | capability manifest |
| `/var/lib/hl-agent/config.json` | hl-agent:hl-agent | 0600 | enrollment config (server URL, CA fingerprint) |
| `/var/lib/hl-agent/outbox.db` | hl-agent:hl-agent | 0600 | encrypted command queue |
| `/etc/sudoers.d/hl-agent` | root | 0440 | sudoers allowlist (read-only to hl-agent) |
| `/etc/systemd/system/hl-agent.service` | root | 0644 | systemd unit (readable by all) |

---

## Advanced: TPM2 key sealing

When available, the agent can seal its Ed25519 signing key in the Trusted Platform Module (TPM2):

**Automatic detection**: during enrollment, install script checks for `/dev/tpmrm0` and `tpm2_getcap`. If present and functional, keys are TPM-sealed by default.

**Storage**: sealed key material stored at `/var/lib/hl-agent/signing.key.tpm` (file falls back if TPM unavailable).

**Unsealing**: TPM is unlocked with a random passphrase stored alongside the sealed key file (still encrypted via the hl-agent user's umask).

**Trade-off**: TPM sealing prevents key extraction even if `/var/lib/hl-agent/` is copied wholesale. Downside: kernel updates may invalidate PCR sealing policies (handled by re-seal flow in update engine, C4).

**Attestation**: agent can prove key residency to server via TPM quote (planned in C2 RBAC work).

---

## Future work (post-v1.0)

- **Plugin runtime hardening** (C6): bwrap default with full seccomp filter; rootless-podman recommended.
- **Per-command approval gates** (C2): high-risk commands trigger async admin approval before agent exec.
- **Rich RBAC** (C3): per-admin roles + permissions; audit per-role changes.
- **Mandatory access controls (SELinux/AppArmor)** (C11): optional hardening for advanced deployments.

---

## References

- **Master plan**: `/home/user/.claude/plans/i-have-a-lot-curried-gizmo.md` (Security Model section)
- **C1 spec**: `docs/superpowers/specs/2026-05-02-hlh-c1-transport-design.md` (Privilege Model section)
- **Threat model**: `docs/security/threat-model.md`
- **Recovery & incident response**: `docs/security/recovery.md`
