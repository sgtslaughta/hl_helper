---
title: Recovery and Incident Response
status: stable
---

# Recovery and Incident Response

This document describes recovery procedures for common failure scenarios and security incidents in hl_helper.

---

## Lost root CA key

**Severity**: **Critical** — all enrolled hosts become unreachable.

### Symptoms

- Server starts but agents cannot connect (TLS handshake fails)
- Error: `CA root.key not found`
- Admin cannot enroll new hosts

### Immediate response

**Do not panic.** Root CA key is backed up offline at install time (assumed). Restore from backup within 1 hour.

### Recovery procedure

1. **Obtain offline backup**: Retrieve encrypted root CA key from offline storage
   ```bash
   # Backup should be at: /offline/secure/fleet-root-ca.enc
   # Decrypt: openssl enc -aes-256-cbc -d -in fleet-root-ca.enc -out root.key
   ```

2. **Restore to server**:
   ```bash
   sudo cp root.key /data/ca/root.key
   sudo chown root:root /data/ca/root.key
   sudo chmod 0600 /data/ca/root.key
   ```

3. **Restart server**:
   ```bash
   sudo systemctl restart fleet-server
   # Verify: sudo systemctl status fleet-server
   ```

4. **Verify agents reconnect**:
   - Check UI: hosts should return to "online" within 30 seconds
   - Check logs: `sudo journalctl -u fleet-server | grep "CA initialized"`

5. **Audit incident**:
   ```bash
   fleet audit log "recovery.root_ca_restored" --data '{"reason":"backup_restore", "confirmed_by":"admin_id"}'
   ```

### Prevention

- Backup root CA key **immediately after first install**: `sudo cp /data/ca/root.key /offline/secure/fleet-root-ca.key.enc` (encrypt with `openssl enc`)
- Store in physically secure location (safe, vault, off-site)
- Rotate backup annually
- Test restore procedure once per year (disaster-recovery drill)

---

## Lost server signing key

**Severity**: **High** — cannot sign new commands; cannot verify old audit entries.

### Symptoms

- New commands fail: `error signing CommandEnvelope`
- Agents see signature verification failures (but trust old keys from anchor list)
- Audit chain unverifiable beyond the point of loss

### Immediate response

**Partial outage**: commands cannot be issued until key is restored or rotated. Agents remain connected but reject all new commands (they await valid signature).

### Recovery procedure

#### Option A: Restore from recent backup (preferred)

1. **Obtain backup**:
   ```bash
   # Should be at: /backup/fleet-signing-key-<YYYY-MM-DD>.enc
   sudo cp /backup/fleet-signing-key-2026-04-30.enc /data/signing/current.key.enc
   sudo openssl enc -aes-256-cbc -d -in /data/signing/current.key.enc -out /tmp/signing.key
   ```

2. **Restore**:
   ```bash
   sudo cp /tmp/signing.key /data/signing/current.key
   sudo chown root:root /data/signing/current.key
   sudo chmod 0600 /data/signing/current.key
   sudo shred -u /tmp/signing.key  # securely wipe temp
   ```

3. **Restart**:
   ```bash
   sudo systemctl restart fleet-server
   ```

4. **Audit**:
   ```bash
   fleet audit log "recovery.signing_key_restored" --data '{"backup_date":"2026-04-30"}'
   ```

#### Option B: Generate new signing key (if backup unavailable)

1. **Rotate to new key**:
   ```bash
   fleet signing-key rotate --grace 7d --force-new
   # Creates new key; old key (if available) moved to anchors/ with grace
   ```

2. **Impact**:
   - All new commands signed with new key
   - Agents trust new key (have anchor list)
   - Audit entries signed by old key remain verifiable (if old key is in anchors/)
   - If old key lost entirely: audit verification from old entries fails until human review

3. **Repair audit chain**:
   ```bash
   fleet audit verify --repair  # flags gaps, suggests forensic snapshot
   ```

4. **Notify admins**:
   - Email: "Signing key rotated due to loss; audit chain has unverifiable gap [time range]"
   - Log security incident for compliance

### Prevention

- Backup signing key weekly (encrypted)
- Separate backup from database backups (signing key + database needed for full recovery)
- Rotate signing key annually (proactive, with grace period) to limit impact of loss

---

## Compromised enrolled host

**Severity**: **Medium** — single host is hostile; other hosts + server not affected.

### Symptoms

- Admin discovers host has been compromised (e.g., rootkit found, unusual network traffic)
- Or: preventive decommission before exploitation spreads

### Recovery procedure

1. **Immediate decommission**:
   ```bash
   # UI: Host page → Decommission → Confirm
   # Or CLI: fleet hosts decommission <host_id> --reason "security_incident"
   ```

2. **Server actions** (atomic):
   - Close active gRPC stream to agent (within 2 seconds)
   - Revoke cert: add serial to CRL
   - Mark host as `decommissioned`
   - Write audit entry: `host.decommissioned` with reason

3. **Agent actions** (if stream still open):
   - Agent receives `Decommission` RPC
   - Wipes all keys, certs, manifest from disk
   - Disables systemd service
   - Writes `/var/lib/hl-agent/decommission.log` with timestamp + admin ID

4. **Forensics**:
   - Preserve host for forensic analysis (do NOT reboot immediately)
   - Capture logs: `journalctl > /tmp/hl-agent.log` (before reboot)
   - Take disk snapshot (if VM)
   - Contact security team

5. **Re-enroll** (if host is recovered):
   - After forensics complete + malware confirmed removed
   - Issue new bootstrap token
   - Run install script again (replaces all agent files)
   - Verify clean enrollment + healthy heartbeat

### Prevention

- **Monitor unusual behavior**: alert on agents that miss heartbeats repeatedly, then reconnect from different IP, or request many new capabilities
- **Capability manifest**: limit risky commands (shell_exec, reboot) to specific hosts by policy
- **Approval gates**: high-risk commands require admin approval (planned in C2 RBAC)

---

## Compromised admin session token

**Severity**: **High** — attacker has admin privileges; can impersonate admin.

### Symptoms

- Admin reports token leaked (e.g., found in Git history, email forwarded, browser history)
- Or: suspicious activity detected (commands issued from unexpected IP, off-hours)

### Recovery procedure

1. **Invalidate token immediately**:
   ```bash
   # UI: Settings → Security → Sessions → Revoke [token]
   # Or CLI: fleet auth revoke-token --pattern "hls_*" (revokes all)
   # Or ENV: update FLEET_ADMIN_TOKEN in docker compose + restart
   ```

2. **Force re-authentication** (v1.0):
   - All active sessions are invalidated
   - Admin must log in again

3. **Audit suspicious actions**:
   ```bash
   fleet audit log list --actor <admin_id> --since "1 hour ago" --format json
   # Review for: unauthorized commands, host decommissions, token mints, setting changes
   ```

4. **Rollback if needed**:
   - If attacker issued commands: manually decommission affected hosts + re-enroll
   - If attacker changed settings: restore from backup or manually revert via CLI

5. **Notify security team**:
   - Document token compromise
   - Update incident log
   - Schedule security review

### Prevention (planned in C3)

- **Per-admin authentication**: bootstrap + local accounts + OIDC + WebAuthn
- **Session binding**: IP + User-Agent fingerprinting; re-auth if changed
- **Approval gates**: high-risk actions (decommission, setting change) require second factor even within session
- **Token rotation**: auto-rotate on password change

---

## Audit log tampering

**Severity**: **Medium-High** — audit integrity questioned; compliance impact.

### Symptoms

- `fleet audit verify` reports hash-chain mismatch
- Admin discovers inconsistencies in audit log (e.g., entry timestamps out of order)
- Database shows modification (audit table has been updated)

### Recovery procedure

1. **Verify chain**:
   ```bash
   fleet audit verify --detailed
   # Output: list of entries, prev_hash match status, signature validity
   ```

2. **Identify tampering**:
   - Note entry ID where mismatch begins
   - Entries before ID are trusted (hash chain valid)
   - Entries after ID are suspect

3. **Inspect Merkle checkpoint** (if available):
   ```bash
   fleet audit checkpoint list
   # Check signatures on checkpoints
   ```

4. **Capture forensic snapshot**:
   ```bash
   fleet audit dump --since <time_before_tampering> --format json > audit_snapshot.json
   fleet audit dump --since <time_before_tampering> --format json | gpg -e -r security@domain > audit_snapshot.json.enc
   # Send to security team (off-server, encrypted)
   ```

5. **Determine scope of corruption**:
   - Was tampering limited to recent entries, or is entire log suspect?
   - Were checkpoints also tampered?
   - Is database backup available for comparison?

6. **Decision on remediation**:
   - If < 1 hour of data lost: truncate audit from last known-good checkpoint + continue
     ```bash
     fleet audit truncate --from-checkpoint <checkpoint_id>
     ```
   - If large gap: must contact data protection officer (audit-log integrity is non-negotiable for compliance)

7. **Audit the audit incident**:
   ```bash
   fleet audit log "audit.tampering_detected" --data '{
     "first_suspect_entry": 12345,
     "truncated_to_entry": 12340,
     "reason": "hash_chain_mismatch_detected"
   }'
   ```

### Prevention

- **Hash chain**: every entry includes hash of previous entry; tampering is detectable
- **Signatures**: periodic Merkle checkpoints are signed with server signing key; tampering detected on verification
- **Immutability**: audit table append-only (no UPDATE/DELETE — use migrations to block)
- **Read-only mode**: backup audit to read-only storage weekly (e.g., object storage with versioning + MFA delete)

---

## Compromise of admin credentials (pre-OIDC, v1.0)

**Severity**: **Critical** — in v1.0, single bootstrap token grants full admin access.

### Symptoms

- Bootstrap token found in logs, config, Git history
- Unauthorized person able to log in to UI as admin

### Recovery procedure

1. **Rotate FLEET_ADMIN_TOKEN**:
   ```bash
   # Generate new token
   openssl rand -base64 32  # or use: fleet auth mint-admin-token
   
   # Update server config
   export FLEET_ADMIN_TOKEN="new-secret-token"
   sudo systemctl restart fleet-server
   ```

2. **Revoke old token**:
   - Any clients using old token will receive 401 Unauthorized
   - Update any automation / CI/CD to use new token

3. **Audit compromised actions**:
   ```bash
   fleet audit log list --actor "bootstrap" --since "1 week ago"
   ```

4. **Migrate to C3 (planned)**:
   - Set up OIDC provider (GitHub, Keycloak, etc.)
   - Create per-admin accounts
   - Require WebAuthn + TOTP
   - Decommission bootstrap token

### Prevention

- **v1.0**: treat FLEET_ADMIN_TOKEN as a secret (Vault, .env.local, never in Git)
- **v1.1+**: migrate to per-admin accounts + OIDC + MFA immediately

---

## Lost agent (disk failure, etc.)

**Severity**: **Low** — single host loss; other hosts unaffected.

### Symptoms

- Host disk failure; new OS installed
- Agent keys and config lost

### Recovery procedure

1. **Decommission old host** (optional; automatic if cert expired):
   ```bash
   fleet hosts decommission <old_host_id> --reason "disk_failure"
   ```

2. **Re-enroll new host**:
   - New host_uuid will be assigned
   - Get new bootstrap token: UI → "Enroll Host"
   - Run install script on new/recovered host
   - Agent enrolls as new host (old host_id not reused)

3. **Verify**:
   - New host appears in UI with new host_id
   - Old host entry can be archived or deleted (if decommissioned)

---

## Data directory corruption or loss

**Severity**: **Critical** — root CA, signing keys, database all at risk.

### Symptoms

- Server fails to start: `database corruption detected`
- `<data_dir>` deleted or inaccessible
- Filesystem errors on `<data_dir>` mount

### Recovery procedure

1. **Assess damage**:
   ```bash
   ls -la /data/  # what's intact?
   sudo sqlite3 /data/fleet.db "PRAGMA integrity_check;"  # database recoverable?
   ```

2. **Restore from backup** (only option if data is lost):
   ```bash
   sudo systemctl stop fleet-server
   sudo rsync -avz /backup/data-2026-05-01/ /data/  # or tar, cp, etc.
   sudo systemctl start fleet-server
   ```

3. **Verify restore**:
   - Check logs: `journalctl -u fleet-server`
   - Verify agents reconnect (within heartbeat timeout)
   - Spot-check audit log: `fleet audit log list | head`

4. **Determine data loss window**:
   - Backup timestamp: 2026-05-01 10:00 UTC
   - Current time: 2026-05-01 14:30 UTC
   - Lost: 4.5 hours of changes (new enrollments, commands, settings)
   - Commands issued during gap will be re-queued by agents (from outbox)

5. **Communicate**:
   - Notify users: "System recovered from backup; changes made between [time1] and [time2] may be lost"

### Prevention

- **Daily backups**: `<data_dir>` to offsite (encrypted, replicated)
- **Database replication**: if HA, use Postgres with streaming replication
- **Filesystem monitoring**: RAID + disk health monitoring
- **Snapshots**: if on VM/storage with snapshot support, snapshots every 6 hours

---

## Network outage / mass agent disconnection

**Severity**: **Medium** — hosts are offline but keys intact.

### Symptoms

- Many agents marked "offline" in UI
- Server logs show `stream closed` for multiple hosts
- Network is actually down (confirmed with IT)

### Recovery procedure

1. **No action required on server side** — agents will reconnect automatically
2. **Verify network**:
   ```bash
   ping -c 1 <agent_ip>  # should respond when network restored
   ```

3. **After network restored**:
   - Agents will reconnect with exponential backoff (default: max 30 minutes)
   - No data loss (agents cache commands locally + replay results from outbox)
   - Audit log records `agent.reconnected` for each agent

4. **Speed up reconnect** (optional):
   - On host: `sudo systemctl restart hl-agent` (forces immediate reconnect)
   - Or: wait up to 30 minutes (default max backoff)

### Prevention

- **Heartbeat interval tuning**: default 30s may be too frequent for unreliable networks; consider 2–5 min for WAN/satellite
- **Outbox capacity**: default 100 MB; adequate for >1 week of typical command/result traffic

---

## Server database corruption (SQLite/Postgres)

**Severity**: **Medium** — audit log or host data at risk.

### Symptoms

- `PRAGMA integrity_check` fails on SQLite
- Server won't start: `database is locked` or `disk I/O error`
- Postgres connection fails: `WAL corruption detected`

### Recovery procedure

#### SQLite (default)

1. **Attempt auto-repair**:
   ```bash
   sudo systemctl stop fleet-server
   sudo sqlite3 /data/fleet.db "REINDEX;"
   sudo systemctl start fleet-server
   ```

2. **If reindex fails**: restore from backup

3. **Check backups**:
   ```bash
   ls -la /backup/fleet.db.*
   sudo sqlite3 /backup/fleet.db.2026-05-01 "PRAGMA integrity_check;"  # find last good backup
   sudo cp /backup/fleet.db.2026-05-01 /data/fleet.db
   sudo systemctl start fleet-server
   ```

#### Postgres (HA mode)

1. **Promote replica** (if available):
   ```bash
   # On replica:
   sudo -u postgres pg_ctl promote
   # Update connection string in fleet-server config
   sudo systemctl restart fleet-server
   ```

2. **If no replica**: restore from WAL backup
   ```bash
   # Contact Postgres DBA
   ```

---

## Agent malfunction (crashes, memory leak)

**Severity**: **Low** — single host restart; all data preserved.

### Symptoms

- Agent process dies repeatedly (watched by systemd, auto-restarts)
- Agent memory usage grows unbounded
- Agent logs show panics / Go runtime errors

### Recovery procedure

1. **Check logs**:
   ```bash
   sudo journalctl -u hl-agent --no-pager | tail -100
   ```

2. **Restart agent**:
   ```bash
   sudo systemctl restart hl-agent
   sudo systemctl status hl-agent
   ```

3. **If crash persists**:
   - Check disk space: `df -h /var/lib/hl-agent`
   - Check dmesg for OOM: `sudo dmesg | tail`
   - Check for hardware issues: `sudo smartctl -a /dev/sda`

4. **Collect diagnostics**:
   ```bash
   sudo journalctl -u hl-agent -o json > /tmp/hl-agent-logs.json
   tar czf /tmp/hl-agent-debug.tar.gz /var/lib/hl-agent/ /tmp/hl-agent-logs.json
   # Send to support / developers
   ```

5. **Upgrade agent**:
   - If known bug: `fleet agent upgrade <host_id>`
   - New binary downloaded + installed + service restarted

---

## Multi-host incident (ransomware, policy misconfiguration)

**Severity**: **Critical** — potential control-plane compromise or mass-host compromise.

### Symptoms

- Multiple agents all fail simultaneously
- All agents receive same error (e.g., policy misconfiguration caused invalid manifest)
- Ransomware detected on multiple hosts

### Recovery procedure

1. **Pause all commands**:
   ```bash
   fleet settings set fleet.commands_paused=true
   # Agents will reject new commands; existing outbox commands still execute
   ```

2. **Investigate root cause**:
   - Check audit log for recent manifest updates or setting changes
   - Query database: `SELECT * FROM audit_entry WHERE action ~ 'manifest|policy' ORDER BY at DESC LIMIT 10;`

3. **Isolate affected hosts**:
   - Bulk decommission if ransomware: `fleet hosts decommission --tag security_incident`
   - Or: revoke capability to risky commands: `fleet settings set capability_manifest.shell_exec=false`

4. **Root cause analysis**:
   - Was policy change legitimate? Who authorized it?
   - Are there signs of admin compromise?
   - Did attacker exploit a server vulnerability?

5. **Recovery**:
   - If admin token leaked: rotate (see Compromised admin session token)
   - If server compromised: full forensic analysis required; consider full data wipe + restore from clean backup
   - Patch + update all hosts
   - Re-enroll hosts with clean policy

---

## Running a disaster-recovery drill

Once per year, practice recovery procedures:

```bash
# Simulate root CA key loss
sudo mv /data/ca/root.key /data/ca/root.key.bak

# Verify: server won't start
sudo systemctl stop fleet-server
sudo systemctl start fleet-server  # should fail

# Recover
sudo mv /data/ca/root.key.bak /data/ca/root.key
sudo systemctl start fleet-server  # should succeed

# Verify agents reconnect
# Check UI within 30 seconds
```

Document findings. Update runbooks.

---

## References

- **Key management**: `docs/security/key-management.md`
- **Threat model**: `docs/security/threat-model.md`
- **Enrollment**: `docs/security/enrollment.md`
- **Agent privilege model**: `docs/security/agent-privilege-model.md`
