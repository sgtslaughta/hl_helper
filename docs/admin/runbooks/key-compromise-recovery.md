---
title: Key Compromise Recovery
status: stable
---

# Key Compromise Recovery

Recovery procedures for three critical security incidents: agent private key compromised, server CA compromised, or audit checkpoint signing key compromised.

---

## Scenario 1: Agent Private Key Compromised

**Severity**: Medium — one agent exposed; other hosts/server safe (mTLS prevents agent-to-agent communication).

**Detection**: Malware/rootkit on host, unauthorized TLS key access in logs, agent used to forge results, or physical access.

**Immediate (1 hour)**:

```bash
# Decommission the host (revokes cert + signing key)
fleet hosts decommission <host_uuid> --reason "security.key_compromise"
# Server closes gRPC stream; agent wipes keys from disk; audit entry written
```

**Recovery (24–48 hours)**:

1. **Preserve host for forensics** (do NOT reboot):
   - VM: `virsh snapshot-create-as <name> incident-<date>`
   - Physical: `sudo dd if=/dev/sda of=/mnt/external/disk-image.dd bs=4M`

2. **Audit impact** (was the key used?):
   ```bash
   fleet audit log list \
     --resource-id "<host_uuid>" \
     --action "result.submitted" \
     --since "7 days ago" --format json > /tmp/results.json
   # Verify each result's signature (server validates automatically)
   ```

3. **Re-enroll** (if malware removed and OS is clean):
   ```bash
   # Full wipe + fresh OS install from golden image
   # Issue new bootstrap token
   fleet hosts bootstrap-token issue
   # Re-run enrollment on host
   ```

4. **Verify**:
   ```bash
   fleet audit verify  # Hash chain intact?
   openssl crl -in /data/ca/crl.pem -noout -text  # CRL published?
   ```

---

## Scenario 2: Server CA Compromised

**Severity**: Critical — attacker can sign arbitrary host certs, impersonating agents.

**Detection**: Unauthorized cert issued, server filesystem breached (`/data/ca/`), backup stolen, or proactive rotation due to incident.

!!! warning "Act Immediately"
    Compromised CA allows attacker to enroll rogue agents. Delay increases exposure window.

**Immediate (30 min)**:

```bash
# Revoke all agents (invalidates current connections)
fleet hosts revoke-all --reason "ca_compromise"
# All agent TLS certs added to CRL; streams close within 2s
# Notify all operators: "All hosts must re-enroll with new CA within 24h"
```

**Recovery (4–12 hours)**:

1. **Rotate CA** (server-side, minimal outage):
   ```bash
   fleet ca rotate --new-key-size 4096 --validity-days 3650
   # Creates /data/ca/root.key.new + .crt.new
   # Old key moved to /data/ca/archive/ (encrypted backup)
   # Stored in /data/ca/anchors/ for old signature verification
   
   fleet ca activate --confirm
   # Switches to new CA immediately
   ```

2. **Re-enroll all agents** (batched, 10% at a time):
   ```bash
   # Generate bootstrap tokens + re-enrollment script
   fleet hosts generate-reenroll-script --output /tmp/reenroll.sh --include-ca-bundle
   fleet hosts bootstrap-token issue --count 50 --output /tmp/tokens.csv
   
   # Phase 1: Test on 1 host
   curl -s https://fleet.example.com/enroll?token=<token> | sudo bash
   
   # Phase 2: Batch 10% with Ansible (or config mgmt)
   ansible-playbook reenroll.yml --limit 'group_10pct'
   
   # Monitor: watch progress with:
   fleet hosts list | jq '.[] | .status' | sort | uniq -c
   ```

3. **Verify**:
   ```bash
   # All hosts back online?
   fleet hosts list --format json | jq '.[] | select(.status != "online")' | wc -l
   # Should be 0
   
   # Audit chain valid?
   fleet audit verify
   ```

**Outage**: ~5 min rotation + 4–24 hours re-enrollment (agents offline during window).

---

## Scenario 3: Audit Checkpoint Signing Key Compromised

**Severity**: Medium-High — future checkpoints can be forged; past entries protected by hash chain.

**What this means**: Merkle checkpoints signed with `/data/signing/current.key`. Before compromise: tampering detected (signature breaks). After: tampering undetectable until next rotation. Past entries remain protected by hash chain.

**Detection**: Attacker gained filesystem access to `/data/signing/`, backup stolen, or disgruntled admin exported key.

**Immediate (1 hour)**:

```bash
# Identify last known-good checkpoint
fleet audit checkpoint list --limit 1

# Rotate key immediately
fleet signing-key rotate --grace 7d --force-new
# Creates /data/signing/current.key.new
# Moves old to /data/signing/archive/ (encrypted)
# Stores old in /data/signing/anchors/ for verification

# Publish update (agents need old key in anchors for verification)
fleet manifest update --include-old-signing-keys
```

**Recovery (1–7 days)**:

1. **Document the compromise window**:
   ```bash
   # Find first untrustworthy checkpoint after compromise time T_c
   fleet audit checkpoint list --format json \
     | jq ".[] | select(.created_at > \"$T_c\")" | head -1
   
   # Create attestation
   echo "Last-known-good-checkpoint: <checkpoint_id>" | sudo tee /data/audit/attestation.txt
   ```

2. **Verify audit integrity** (entries up to last good checkpoint):
   ```bash
   fleet audit verify --checkpoint <checkpoint_id>
   # Output: "Hash chain valid from genesis to checkpoint"
   
   # Backup last good state (encryption required)
   fleet audit dump --until-checkpoint <checkpoint_id> --format json \
     | gpg -e -r security@domain > /backup/audit-pre-compromise.json.gpg
   ```

3. **Monitor post-rotation** (new checkpoints use new key):
   ```bash
   fleet audit verify --detailed
   # Should report: "Signature valid" for all new entries
   ```

**Compliance**: Document unverifiable gap in audit; contact forensics if tampering detected during gap.



---

## Post-Incident Verification

Run these queries after any key compromise to verify fleet integrity:

```bash
# Query 1: Unauthorized certs after incident (Scenario 2 recovery)
fleet audit log list --action "host.certificate.issued" \
  --since "2026-05-01T00:00:00Z" --format json \
  | jq '.[] | {host_id, issued_by}'

# Query 2: Forged results (invalid signatures)
fleet audit log list --resource-type "host" \
  --action "result.submitted" --since "2026-05-01T00:00:00Z" --format json \
  | jq '.[] | select(.signature_valid == false)'

# Query 3: Re-enrollment progress (Scenario 2 recovery)
fleet audit log list --action "host.enrolled" \
  --since "2026-05-01T00:00:00Z" --format json \
  | jq -r '.[] | .created_at' | sort | uniq -c

# Query 4: Checkpoint signature validity (Scenario 3 recovery)
fleet audit checkpoint list --format json \
  | jq '.[] | {id, signature_valid, signed_with_key}'
```

## References

- [Key Management](../security/key-management.md) — rotation procedures, backup policy
- [Recovery and Incident Response](../security/recovery.md) — general incident procedures
- [Threat Model](../security/threat-model.md) — security assumptions & threat coverage
- [HA Topology](./ha-topology.md) — backup and disaster recovery
