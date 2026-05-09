---
title: Incident Response
status: stable
---

# Incident Response

An incident is when something goes wrong — a security breach, a data loss, a compromised host, or a service outage. This page covers how to think about incidents and respond to them in a structured way. The next page shows the practical runbooks.

## What Is an Incident?

An incident is a deviation from normal operation that requires action. Examples:

- **Security incident**: A host is compromised; credentials are leaked; an attacker gained unauthorized access.
- **Availability incident**: The server is down; agents can't connect; the database is corrupted.
- **Compliance incident**: An audit log was tampered with; access control was bypassed; a backup failed.

Not everything is an incident. A log message is not an incident. A slow API call is not an incident (unless it's causing downtime). An incident is something that threatens your system's security, availability, or integrity.

## The Incident Response Lifecycle (NIST 800-61)

NIST (US National Institute of Standards and Technology) defines a framework for incident response in five phases. Here's the homelab version:

### 1. Detection

Someone notices something is wrong.

- **Automated**: An alert fires (e.g., "cert expires in 1 day", "server hasn't checked in").
- **Manual**: An admin notices odd behavior (e.g., "Why is the SSH key in Slack?").

**Action**: Log the incident. Write down the time, what you observed, and why you think it's a problem.

### 2. Containment

Stop the bleeding. Prevent the incident from getting worse.

**Example: Compromised host**

Action: Isolate the host from the network (unplug it, revoke its certificate, or firewall it). This prevents the attacker from pivoting to other machines.

**Example: Leaked database password**

Action: Change the password immediately. Revoke any connections using the old password. This prevents an attacker from accessing the database.

**Example: Audit log tampering**

Action: Stop the server and take a filesystem snapshot. Preserve evidence.

Containment is **urgent** — do it before investigating, before understanding root cause. Speed matters.

### 3. Eradication

Remove the threat. Fix the root cause.

**Example: Compromised host**

After isolation, you investigate: "How was it compromised?" (maybe a kernel vulnerability, a malicious package, or a weak password). Then you fix the root cause (patch the kernel, remove the malicious package, force a password reset).

**Example: Leaked password**

You investigate: "Where did the password come from?" (maybe a screenshot, a config file, a log). Then you fix it (delete the screenshot, remove the password from the config file, rotate log retention).

Eradication can take time. You should do it in a controlled way (test in staging first).

### 4. Recovery

Bring the system back to normal operation.

**Example: Compromised host**

Once you've fixed the root cause, you:
1. Verify the fix (test the patch, run a scan for malware, check logs).
2. Re-enroll the host (issue a new certificate, new signing key).
3. Verify the agent reconnects and can receive commands.
4. Monitor for a few hours to confirm it's stable.

**Example: Audit log tampering**

Once the server is secured:
1. Verify the filesystem is clean (run checksums, compare against backups).
2. Restore the audit log from a backup (or recreate the missing entries from other sources).
3. Restart the server.
4. Monitor for further tampering.

### 5. Lessons Learned

After the incident is over, do a post-mortem.

**Questions to ask**:

- What happened? (Timeline)
- Why did it happen? (Root cause)
- What did we do right? (What helped us respond fast)
- What could we do better? (What slowed us down)
- What do we change to prevent this in the future? (Process, automation, monitoring)

**Example**: "We detected a compromised host because an alert fired for cert rotation failure. But it took 2 hours to realize what the alert meant. Let's improve the alert message and add a dashboard showing all failed cert rotations."

## Roles in a Homelab Incident Response

In an enterprise, you have an incident response team: a security officer, a on-call engineer, a communications person, etc. In a homelab, you might be doing all of this yourself. But the roles are still useful to think about:

| Role | Responsibility | Example |
|---|---|---|
| **Incident Commander** | Makes decisions, coordinates response | "We're isolating the server now. Please verify backups are available." |
| **Technical Lead** | Investigates, executes fixes | "I found the malicious package in the logs. Removing it now." |
| **Communications** | Notifies stakeholders | "The server will be down for 2 hours while we recover." |
| **Evidence Collector** | Preserves logs, snapshots, data | "I took a filesystem snapshot before making any changes." |

Even if you're one person, keep these roles in mind mentally. When you're in "incident commander" mode, you're thinking strategically. When you're in "technical lead" mode, you're debugging.

## Communication During an Incident

If other people use your homelab (family members, colleagues), keep them informed:

1. **Initial notification**: "We've identified a problem. We're investigating."
2. **Status updates**: "We've contained the issue. Expected recovery time: 2 hours."
3. **Resolution**: "The issue is fixed. Everything is back to normal."
4. **Post-mortem**: "Here's what happened, why, and what we're doing to prevent it."

Bad communication (silence) breeds panic. Good communication keeps people calm.

## Evidence Preservation

Before you make any changes, preserve evidence.

Examples:

- **Filesystem snapshot**: Before deleting a suspicious file, take a `btrfs snapshot` or `lvm snapshot` so you can inspect it later.
- **Log backup**: Copy `/var/log/` somewhere safe before rotating logs.
- **Memory dump**: If a process crashed, capture `coredump` before restarting.
- **Network capture**: If you suspect network tampering, capture traffic with `tcpdump`.

Evidence helps with:
- Root cause analysis (why did this happen?).
- Forensics (who did this?).
- Legal/compliance (proving you took action).
- Learning (post-mortem analysis).

## Severity and Response Time

Incidents have different urgency levels:

| Severity | Definition | Response Time | Example |
|---|---|---|---|
| **Critical** | Total outage; keys lost; audit integrity broken | < 30 minutes | Server won't start; root CA key is missing |
| **High** | Major impact; one critical component down | < 2 hours | Admin token compromised; signing key leaked |
| **Medium** | Partial impact; degraded service | < 24 hours | One host compromised; certificate expiry failed |
| **Low** | Minor impact; no immediate action needed | < 7 days | Informational alert; non-critical log error |

Use this to decide *how* to respond:

- **Critical**: Wake up at 3 AM. Call the team. Use emergency procedures.
- **High**: Respond during business hours. Use standard procedures.
- **Medium**: Respond within 24 hours. Can wait until morning.
- **Low**: Log it. Address at next maintenance window.

## Mental Preparation

Incidents are stressful. Before you have one, prepare mentally:

1. **Don't panic**: Most incidents are recoverable. You have backups. You have isolation tools.
2. **Preserve evidence**: Before fixing, preserve. This helps forensics later.
3. **Verify before and after**: Test your fix in staging first, if possible.
4. **Document as you go**: Write down what you did and why. This helps the post-mortem.
5. **Ask for help**: If you're stuck, ask in a forum, a Slack channel, or a Discord community.

## Common Incident Types and Quick Responses

### "A Host Is Compromised"

1. **Contain**: Disconnect the host from the network (unplug network cable or firewall it).
2. **Preserve**: Take a filesystem snapshot if possible.
3. **Investigate**: What was the attack vector? (weak password, unpatched kernel, malicious package)
4. **Eradicate**: Fix the root cause.
5. **Recover**: Re-enroll the host with a new certificate and signing key.

### "The Server Is Down"

1. **Contain**: Check if it's a hardware failure, a power issue, or a software crash.
2. **Preserve**: Check logs for errors before restarting.
3. **Investigate**: Look at the last few log lines. What was running?
4. **Eradicate**: Restart the server. If it crashes again, investigate further.
5. **Recover**: Monitor for stability. Check agents reconnect.

### "Credentials Are Leaked"

1. **Contain**: Revoke the credential immediately (change password, delete API key).
2. **Preserve**: Check logs to see who accessed what with the leaked credential.
3. **Investigate**: How was it leaked? (Slack, email, screenshot, config file)
4. **Eradicate**: Remove the credential from all places it was stored.
5. **Recover**: Rotate all related credentials (if one password is leaked, assume others are too).

### "An Alert Is Firing But I Don't Know Why"

1. **Contain**: Suppress the alert if it's a false positive. Otherwise, treat it as a potential incident.
2. **Investigate**: Read the alert details. Is there a pattern?
3. **Escalate**: If you can't figure it out in 10 minutes, ask for help.

## Related Pages

- [Runbooks](./41-runbooks.md) — Step-by-step procedures for common incidents
- [Recovery](../runbooks/recovery.md) — Detailed recovery procedures
- [Key Compromise Recovery](../runbooks/key-compromise-recovery.md) — Security incident procedures
