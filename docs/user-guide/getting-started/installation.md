---
title: Installation
status: stable
---

# Installation

!!! note "End user vs admin"
    This page covers end-user setup of the web UI on your workstation. For server and agent deployment, see [Administration → Deployment](../../admin/deployment/).

## Browser Access

As an end user, you don't need to install HL Helper—you just access it via your web browser.

### System Requirements

- **Browser**: Any modern browser (Chrome, Firefox, Safari, Edge)
  - JavaScript must be enabled
  - Cookies must be enabled for sessions
- **Internet connectivity**: Access to the URL your admin provided
- **Optional**: For multi-factor authentication (MFA):
  - TOTP authenticator app (Google Authenticator, Authy, etc.)
  - Or a security key (YubiKey, Apple Passkey, etc.)

## First Access

Your admin will provide you with:

1. **The HL Helper URL** (e.g., `https://hlhelper.example.com`)
2. **Your login credentials**:
   - Email or username
   - Temporary password (or a "set password" link)
3. **Optional**: Recovery codes or MFA setup instructions

### First Login

1. Open the URL in your browser
2. You'll see the **Sign In** page
3. Enter your credentials
4. If this is your first login, you may be prompted to:
   - Set a permanent password (if you received a temporary one)
   - Complete a setup wizard (multi-factor auth, etc.)

See [Login & MFA](../features/login.md) for detailed instructions.

### Password Reset

If you forget your password:

1. On the login page, click **Forgot password?**
2. Enter your email
3. Check your email for a reset link
4. Follow the link and set a new password

If password reset is not available, contact your admin—they can trigger a reset for you.

## Browser Preferences

For the best experience:

- **Desktop is recommended** for the full UI experience
- **Mobile and tablet** are supported but some features may be limited
- **Dark mode** is available in settings (personal preference)
- **Bookmarking** the URL makes return visits quick

## Next Steps

- [Quick Start](quickstart.md) — Get oriented in 5 minutes
- [Login & MFA](../features/login.md) — Set up your account and security
- [Overview](overview.md) — Learn key concepts
