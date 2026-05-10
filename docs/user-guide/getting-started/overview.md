---
title: Overview
status: stable
---

# HL Helper for Users

HL Helper is a self-hosted fleet manager for your Linux and Unix machines. It gives you one web interface to see all your hosts, check security issues, and trigger updates or maintenance tasks—all without giving the control plane direct root access to your machines.

Think of it as a security-conscious command center for your homelab or small multi-machine environment. Your administrator sets it up; you log in and use it to monitor and manage your fleet.

## Who This Guide is For

This guide is for **end users and operators**—people with login credentials who use the web interface to:
- Log in and manage your account
- View your fleet of hosts
- See security findings and advisories
- Trigger allowed actions like scans or updates

If you're setting up the server, managing users, or deploying agents to hosts, see [Administration](../../admin/) instead.

## What You Can Do

- **Log in** with your credentials (password, passkey, or SSO)
- **See your fleet**: List of all hosts you have permission to view
- **Check host health**: Uptime, last heartbeat, installed packages, security posture
- **View findings**: CVEs, security misconfigurations, advisory details
- **Trigger actions** (if your role allows):
  - Rescan for vulnerabilities
  - Check for updates
  - Run security checks
- **Manage your account**: Change password, set up multi-factor authentication (passkey or TOTP), download recovery codes
- **Access the terminal** (if enabled by admin): Run commands on hosts via the web UI

## What You Cannot Do (Admin-Only)

- Enroll new hosts
- Create or manage user accounts
- Change roles or permissions
- Modify system settings
- Rotate server keys or certificates

For these tasks, contact your administrator. See [Administration](../../admin/) for the full reference.

## Tour of the Web Interface

### Login Page

Sign in with your email or username and password. If your admin has enabled multi-factor authentication (MFA), you'll be prompted to enter a code or touch your security key.

See [Login & MFA](../features/login.md) for detailed steps.

### Fleet View (Dashboard)

After login, you land on the **Fleet** page. It shows:
- **Host list**: Name, status (online/offline), last heartbeat, number of advisories
- **Filters and search**: Find hosts by name, tag, or status
- **Quick stats**: Total hosts, hosts with pending updates, critical findings

Click a host to see its detail page.

### Host Detail Page

View everything about one host:

- **Status**: Online/offline, uptime, heartbeat time, agent version
- **Posture**: Installed packages, pending updates, security findings
- **Advisories**: CVEs, misconfigurations, with severity and fix guidance
- **Actions**: Trigger scans, updates, or terminal access (if allowed)
- **History**: Past commands and results (audit trail)

### Findings & Advisories

The **Findings** section aggregates security issues across your fleet:

- **List view**: Filter by severity, host, status (new/acknowledged/resolved)
- **Detail**: Each finding shows the issue, affected packages/hosts, and remediation steps
- **Actions**: Mark as acknowledged, view related hosts, download advisory details

### Account & Settings

From the top menu:

- **Change password**: Set a new password (old password required)
- **MFA setup**: Add a passkey or TOTP authenticator
- **Recovery codes**: Download and store backup codes for account recovery
- **API keys** (if admin allows): Create keys for automated access
- **Session management**: View active sessions and log out

## Key Concepts

### Host

A Linux or Unix machine enrolled in HL Helper. The admin installs an agent on it. The host reports its status, packages, and security posture to the control plane.

### Agent

Lightweight program running on each host. It receives commands from the control plane, executes them securely, and reports results. The agent has no ability to access other hosts or the control plane's data.

### Finding

A security issue detected on one or more hosts: a CVE, misconfiguration, or advisory. Findings are aggregated across your fleet so you can see all issues in one place.

### Advisory

An official security bulletin (from NVD, RHSA, USN, etc.) describing a vulnerability and its fix. HL Helper links advisories to affected packages on your hosts.

### Role

Your level of permission in HL Helper. Common roles:

- **Owner**: Full access (rare for regular users)
- **Admin**: User/host management, settings
- **Operator**: View fleet, trigger scans/updates
- **Viewer**: Read-only access to fleet and findings

Your admin controls which actions you can take.

### Scope

A subset of hosts you're allowed to see and manage. Your admin may give you access to only certain hosts, tags, or environments.

## Next Steps

- [Quick Start](quickstart.md) — 5-minute walkthrough
- [Login & MFA](../features/login.md) — Set up your account and security
- [Administration](../../admin/) — For admins and installers
