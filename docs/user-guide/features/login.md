---
title: Login & MFA
status: stable
---

# Login & Multi-Factor Authentication

Secure sign-in for HL Helper: local passwords, multi-factor authentication, and recovery methods.

## First Login

When your admin gives you HL Helper credentials, you'll receive:

- **The server URL** (e.g., `https://hlhelper.example.com`)
- **Your email or username**
- **Your initial password** (or a link to set one)

### First Sign-In Steps

1. Open the server URL in your web browser
2. You'll see the **Sign In** page with two options:
   - **Password** tab: Enter your email/username and password
   - **Admin Token** tab: For initial bootstrap (rarely used as a regular user)
3. On first login, you may see:
   - A **setup wizard** (multi-factor auth, password change)
   - A **dashboard** if your admin pre-configured your account

### Password Requirements

Your password must be:
- **At least 12 characters long**
- **Not a common pattern** (zxcvbn check rejects "password123", "qwerty", etc.)
- **Unique** (optional: check against Have I Been Pwned if your admin enabled it)

We recommend:
- Using a passphrase (e.g., "BlueSky-Giraffe-Umbrella-42")
- A password manager (Bitwarden, 1Password, etc.) to generate and store it
- Avoiding personal information or dictionary words alone

## Signing In

The **Sign In** page shows a simple form:

- **Username or email field**: Enter your email or username (your admin will tell you which)
- **Password field**: Your secret password
- **Sign In button**: Submit to log in

### MFA Challenges During Sign-In

If your role requires multi-factor authentication, after entering your password you'll see:

**Option 1: TOTP (Authenticator App)**
- A prompt for a 6-digit code from your authenticator app
- Enter the code and click **Verify**
- Codes change every 30 seconds, so be quick

**Option 2: WebAuthn / Passkey**
- A prompt to touch your security key or approve a passkey on your device
- Follow your browser's instructions
- Works with YubiKeys, Apple Passkeys, Windows Hello, Android biometric, etc.

After successful MFA, you'll be logged in.

## Remember Me & Session Length

On the sign-in page, you may see a **Remember me** checkbox:

- **Checked**: Your session persists for up to 12 hours (even if you close the browser)
- **Unchecked**: Your session expires after 30 minutes of inactivity

### Session Timeout

Your session automatically expires if:
- **Idle timeout** is reached (usually 30 minutes with no activity)
- **Absolute timeout** is reached (usually 12 hours max, regardless of activity)
- Your admin revokes your session (e.g., due to a password reset)
- Your role or permissions change

If your session expires, you'll be redirected to the sign-in page. Just sign in again.

## Multi-Factor Authentication (MFA) Setup

If your admin requires or recommends MFA, you can set it up in your account settings.

### TOTP (Authenticator App)

Time-based One-Time Password works with any TOTP app: Google Authenticator, Authy, Microsoft Authenticator, FreeOTP, etc.

**Setup:**

1. Go to your profile icon (top right) → **Settings** or **Account**
2. Find **Security** → **Multi-Factor Authentication**
3. Click **Add TOTP**
4. A QR code appears on screen
5. In your authenticator app:
   - Choose "Scan QR code" or "Add manually"
   - Scan the code (or copy the secret key and enter it manually)
6. Your app now shows a 6-digit code that changes every 30 seconds
7. In HL Helper, enter the code to verify it's working
8. On success, you'll see your **recovery codes** (see below)
9. Click **Enable** to activate TOTP

**Using TOTP at sign-in:**

- After entering your password, you'll be asked for a 6-digit code
- Open your authenticator app and copy the current code
- Enter it on the screen
- If the code is correct, you'll be logged in

### WebAuthn / Passkey / Security Key

Works with hardware keys (YubiKey, Titan) or platform authenticators (Apple Passkey, Windows Hello, Android biometric).

**Setup:**

1. Go to your profile → **Settings** → **Security** → **Multi-Factor Authentication**
2. Click **Add WebAuthn** or **Add Passkey**
3. Name your key (e.g., "YubiKey on desk" or "iPhone Passkey")
4. Your browser will prompt you:
   - **Roaming authenticator**: Tap your security key or click "Use a passkey"
   - **Platform authenticator**: Use your device's biometric or PIN
5. Complete the gesture (touch, face scan, fingerprint, etc.)
6. On success, your key is registered
7. You'll see your **recovery codes** (see below)

**Using WebAuthn at sign-in:**

- After entering your password, you'll be asked to touch your security key or approve a passkey
- Follow your browser's instructions
- No code entry needed—it's automatic

**Browser Support:**

- Chrome/Chromium: Full support (USB, BLE, NFC keys; platform authenticators)
- Firefox: Full support
- Safari: Full support (Apple Passkey integrated)
- Edge: Full support
- All require HTTPS (or localhost for testing)

### Recovery Codes

When you set up MFA (TOTP or WebAuthn), HL Helper generates **10 single-use recovery codes**:

- Format: Random strings (e.g., "ABC123-DEF456")
- **Use case**: If you lose your authenticator app or security key, use a recovery code to regain access
- **Critical**: Each code works only once
- **Storage**: Store them in a safe place (password manager, encrypted file, safe deposit box)

**Using a recovery code:**

1. On the MFA challenge screen, click **Use a recovery code** (if available)
2. Paste one of your codes
3. You'll be logged in; the code is then invalid
4. After you regain access, set up a new MFA method and generate new recovery codes

**Regenerating recovery codes:**

1. Go to **Settings** → **Security** → **MFA**
2. Click **Regenerate recovery codes**
3. Old codes become invalid; download and store the new ones immediately

## Lost or Forgotten MFA

### Locked Out?

If you lose your TOTP device or security key:

**Option 1: Use a recovery code**
- You should have stored them somewhere safe
- Go to the MFA challenge screen and select **Use a recovery code**
- Enter one of your codes to log in
- Then set up a new MFA method

**Option 2: Contact your admin**
- Your admin can reset your MFA
- You'll be able to log in with just your password (until you re-enable MFA)
- They may ask you to verify your identity first

### Forgotten Password (With MFA Active)

If you forgot your password and can't reset it by email:

1. You cannot use password reset (because you don't have the password yet)
2. Contact your admin to reset your password for you
3. Or, if you have a recovery code, use it to log in, then change your password immediately

## Password Reset

### Self-Service Password Reset

If you know your current password:

1. Go to your profile → **Settings** or **Account** → **Password**
2. Click **Change password**
3. Enter your **current password** (for verification)
4. Enter your **new password** (must meet complexity rules)
5. Confirm and save

### Forgot Password?

If you forgot your password:

1. On the **Sign In** page, click **Forgot password?**
2. Enter your email address
3. Check your email for a reset link (usually expires in 30 minutes)
4. Follow the link and set a new password
5. Sign in with your new password

**If you don't receive an email:**
- Check spam/junk folders
- Verify you're using the correct email
- Wait a few minutes (email can be slow)
- Contact your admin to resend or reset it for you

### Password Reset via Admin

Your admin can also reset your password without email:

1. Admin generates a reset link
2. Admin shares the link with you (usually via message, not email)
3. You follow the link and set a new password
4. The link becomes invalid

## OIDC / SSO (Single Sign-On)

If your admin enabled single sign-on (SSO), the **Sign In** page shows buttons for external providers:

- **Continue with GitHub**
- **Continue with Google**
- **Continue with Microsoft**
- Custom providers your admin configured

**Using SSO:**

1. Click the provider's button
2. You'll be redirected to the provider's login page
3. Sign in with your provider account (e.g., GitHub credentials)
4. The provider confirms your identity to HL Helper
5. You're automatically logged in (or added as a new user if first time)

**Linking to existing account:**

- If you already have a local password account, your first SSO login can link to it
- HL Helper will ask to confirm (usually by email)
- After linking, you can use either password or SSO to log in

## Logout & Account Security

### Manual Logout

1. Click your profile icon (top right)
2. Click **Logout** or **Sign out**
3. You'll be redirected to the sign-in page
4. Your session is immediately invalidated

### Automatic Logout

- Session expires after 30 minutes of inactivity
- Or 12 hours absolute (whichever comes first)
- You'll be redirected to sign in

### Multi-Device Sessions

You can be logged in on multiple devices (phone, laptop, desktop, etc.) at the same time. Each has its own session that expires independently.

**Revoking all sessions:**

Your admin can force log out all your sessions (e.g., if you suspect a security breach). After that, you'll need to sign in again on all devices.

## Security Best Practices

- **Use a strong, unique password**: Not reused from other sites
- **Store recovery codes safely**: Treat them like passwords
- **Enable MFA**: Use WebAuthn/Passkey if available (more secure than TOTP)
- **Keep your device secure**: Lock your phone/laptop
- **Watch for phishing**: HL Helper will never ask for your password by email
- **Log out on shared devices**: Always click **Logout** after use
- **Report suspicious activity**: If you see unexpected sessions, contact your admin

## Related

- [Quick Start](../getting-started/quickstart.md) — Get started in 5 minutes
- [Overview](../getting-started/overview.md) — Learn key concepts
- [Administration → Security Fundamentals](../../admin/security-fundamentals/) — For admins: password policy, MFA enforcement
