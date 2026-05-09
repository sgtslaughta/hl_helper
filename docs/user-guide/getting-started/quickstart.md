---
title: Quick Start
status: stable
---

# Quick Start for End Users

Get started with HL Helper in 5 minutes. This guide assumes your admin has already deployed the server and sent you login credentials.

## Step 1: Log In

1. Open the HL Helper URL your admin provided (e.g., `https://hlhelper.example.com`)
2. You'll see the **Sign In** page
3. Enter your email or username and password
4. If multi-factor authentication (MFA) is enabled, complete the MFA challenge:
   - For **TOTP**: Open your authenticator app and enter the 6-digit code
   - For **Passkey/WebAuthn**: Touch your security key or approve the prompt on your phone
5. Click **Sign In**

See [Login & MFA](../features/login.md) for detailed instructions.

## Step 2: See Your Fleet

After login, you're on the **Fleet** dashboard:

- **Host list** on the left or center: All machines you have permission to see
- **Status column**: Shows "Online" (heartbeat recent) or "Offline" (no recent heartbeat)
- **Quick stats**: Total hosts, hosts with pending updates, critical findings

Get familiar with the layout. If you don't see any hosts, contact your admin—they may not have enrolled machines yet, or may not have granted you access.

## Step 3: View a Host

Click any host name to open its **detail page**:

- **Status pane**: Uptime, last heartbeat, agent version
- **Posture section**: Operating system, installed packages, pending updates
- **Advisories section**: Security issues (CVEs, misconfigurations) with severity badges
- **History section**: Past actions and results (if available)

This is where you'll spend most of your time monitoring your fleet.

## Step 4: View Findings Across Your Fleet

Click **Findings** in the left menu to see all security issues in one place:

- **Filters**: By severity (critical, high, medium, low), status (new, acknowledged, resolved), or host
- **Search**: Find specific CVEs or issues by name
- **Detail view**: Click a finding to see affected hosts, advisory details, and remediation steps

You can acknowledge findings or mark them resolved after patching.

## Step 5: Trigger a Scan or Update (If Allowed)

If your role permits, you can trigger actions on hosts:

1. Open a host detail page
2. Look for the **Actions** menu or button
3. Choose:
   - **Scan for updates**: Refresh the list of available packages
   - **Scan for vulnerabilities**: Check for new CVEs in installed packages
   - **Other actions**: Your admin may have enabled additional workflows
4. Confirm the action
5. Watch the **History** section for the result

Not all roles can trigger actions—if the button is disabled, contact your admin.

## Next: Manage Your Account

Now that you're in, set up your account:

1. Click your profile icon (top right)
2. Choose **Settings** or **Account**
3. Consider:
   - **Changing your password**: Set a strong, unique password
   - **Setting up a passkey or TOTP**: Enable multi-factor authentication for security
   - **Downloading recovery codes**: Backup codes to regain access if you lose your MFA device

See [Login & MFA](../features/login.md) for step-by-step guides.

## Getting Help

- **Can't log in?** Check your email/username and password. If you've locked your account, contact your admin.
- **Don't see any hosts?** You may not have permission yet—contact your admin.
- **Have questions?** Check the [Overview](overview.md) for key concepts, or ask your admin.

## Related

- [Overview](overview.md) — Concepts and features
- [Login & MFA](../features/login.md) — Account setup and security
- [Features](../features/) — Deep dives into specific UI features
