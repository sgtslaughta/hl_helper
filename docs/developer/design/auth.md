---
title: Authentication
status: stable
---

# Authentication

User authentication covers three domains: local passwords, OIDC/SSO integration, and multi-factor authentication. All flows are audit-logged and produce revocable session tokens bound to device and network context.

---

## Sessions

### Token Format & Lifetime

- **Format**: Opaque `hls_` prefix + 32-byte base32 entropy (~190 bits). Example: `hls_a1b2c3d4e5f6g7h8...`
- **Storage**: SHA-256 hash persisted in DB; plaintext never stored on server.
- **Idle TTL**: 30 minutes (configurable, `FLEET_SESSION_IDLE_TTL`).
- **Absolute TTL**: 12 hours (configurable, `FLEET_SESSION_ABS_TTL`).
- **Sliding window**: Using endpoint refreshes `last_used_at` up to the absolute cap; no extension beyond absolute TTL.

### Transport Variants

**Browser (Cookie)**:
```
Set-Cookie: hls_session=hls_a1b2c3d4...; 
            Secure; HttpOnly; SameSite=Strict; Path=/; 
            Max-Age=<idle-ttl-seconds>
```
Plus a CSRF token (double-submit cookie) for state-changing requests.

**API Client (Bearer)**:
```
Authorization: Bearer hls_a1b2c3d4...
```
No CSRF required (already authenticated by token).

### Session Record Schema

```
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  token_hash BLOB NOT NULL,        -- SHA-256(plaintext token)
  user_id TEXT NOT NULL,
  mfa_level TEXT NOT NULL,         -- none|totp|webauthn|webauthn_attested
  mfa_last_at TIMESTAMPTZ,         -- when last MFA challenge passed
  ip_class TEXT NOT NULL,          -- IPv4 /24, IPv6 /64 hash
  ua_fingerprint_hash BLOB,        -- User-Agent hash (optional)
  created_at TIMESTAMPTZ NOT NULL,
  last_used_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL, -- absolute TTL
  revoked_at TIMESTAMPTZ,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### Revocation

Sessions are **instantly revocable** in these cases:

- Explicit logout (`POST /v1/auth/logout`).
- Password reset by user or admin.
- Role changed (any permission grant/revoke).
- Admin force-logout of a user.
- Suspicious activity flag (anomalous IP, UA, or behavior).

Revocation clears the in-memory session cache and database record; subsequent requests return `401 Unauthorized`.

### Cache

In-memory LRU (size 10k, TTL 30s). Hits avoid DB lookup; misses populate cache. Cache is invalidated on any session write (logout, revoke, MFA update) via an in-process event bus.

---

## Local Authentication

### Bootstrap

On first run, the server generates a 256-bit bootstrap token and:
- Prints it to container logs (once, clearly marked).
- Writes to `/data/.bootstrap-token` (mode 0600, ephemeral).
- TTL: 60 minutes.

Setup wizard consumes this token to create the first owner account. Token is then deleted. Subsequent users are created via admin invite or OIDC JIT provisioning.

### Password Requirements

- **Hashing algorithm**: Argon2id with configurable parameters:
  - Memory: 64 MB (configurable, `FLEET_PASSWORD_ARGON2_M_KIB`).
  - Time: 3 iterations (tuned to ~250ms on commodity hardware).
  - Parallelism: 4 threads.
- **Complexity check**: Minimum 12 characters + zxcvbn score ≥3 (detects weak patterns like "qwerty123").
- **Breach check**: K-anonymity lookup against Have I Been Pwned (optional, off by default for air-gap).
- **Rotation policy**: Disabled by default per NIST 800-63B. Max-age enforcement available if configured.

### Login Flow

1. **Request**: `POST /v1/auth/login` with `{email, password}` (or `{username, password}`).
2. **Lookup**: Query `users` table by email; check not deactivated.
3. **Verify**: Argon2id verify against stored hash. On failure:
   - Increment per-user failure counter (backoff: 1m, 5m, 15m, 1h, 24h after 5 failures in 5min).
   - Increment per-IP failure counter (separate DDoS mitigation).
   - Return `401 Unauthorized` (uniform, no "user not found" leak).
4. **Determine MFA requirement**: Check user's role policy. Possible responses:
   - No MFA required → mint session, return `{session_token, user}`.
   - MFA required → return `{mfa_challenge_id, methods: ["totp", "webauthn"]}` (202 Accepted).
5. **MFA challenge**: `POST /v1/auth/mfa` with `{mfa_challenge_id, method, response}`.
   - Verify TOTP/WebAuthn (see below).
   - On success: mint session with `mfa_level = <method>`, `mfa_last_at = now()`.
   - Return `{session_token, user, mfa_level}`.

### Account Lockout

**Per-user backoff** (5 failures within 5 minutes):
- 1st failure: 1 minute locked.
- 2nd failure: 5 minutes locked.
- 3rd–5th: 15 minutes, 1 hour, 24 hours.
- Reset on successful auth.

**Per-IP DDoS limit**: Separate counter prevents distributed brute force.

### Password Reset

- **SMTP-based** (default): User requests reset → admin sends signed link (30min TTL) via email → user follows link and sets new password.
- **Admin-initiated**: Admin generates a reset link without SMTP → link displayed once in UI (can copy/share) → user follows → sets password.

---

## Multi-Factor Authentication (MFA)

### TOTP (Time-based One-Time Password)

**Enrollment**:
1. User navigates to Settings → Security → MFA.
2. Server generates a random TOTP secret (base32).
3. UI displays QR code (Google Authenticator, Authy, etc.).
4. User scans and enters a 6-digit code to verify secret is working.
5. Server stores secret encrypted at rest via the secrets broker (AES-256-GCM envelope).
6. Recovery codes (10 one-use codes) are generated and displayed once.

**Verification**:
- User provides 6-digit TOTP code.
- Server checks code against current + next time window (30-second slots, RFC 6238).
- On mismatch, increment per-user TOTP-failure counter; 5 failures in 60s → 15min cooldown.

**Algorithm**: SHA-1/256/512 (default SHA-256), 6-digit.

### WebAuthn / FIDO2 / Passkeys

**Enrollment**:
1. User clicks "Add security key".
2. Server initiates `WebAuthn.create()` ceremony:
   - Generate challenge (32 bytes random).
   - RP ID derived from `FLEET_PUBLIC_URL` hostname.
   - User verification required (for both platform and roaming authenticators).
   - Resident key optional (for passkey sync).
3. Browser prompts user to touch YubiKey, Apple Passkey, etc.
4. Device returns attestation object + client data JSON.
5. Server verifies attestation (checks AAGUIDs against known authenticators; strict mode optional).
6. Credential stored: public key, transports, sign-count, user-provided name.
7. Multi-credential support: user can enroll multiple keys.

**Verification**:
- User prompted to touch authenticator.
- Server verifies assertion signature using stored public key.
- Sign-count anomaly detection: if sign-count regresses (e.g., cloned key), credential is flagged and re-verification forced.
- Conditional UI supported: passkey "autofill" on compatible browsers (Chrome, Safari).
- Cross-device (caBLE/hybrid) supported: QR code prompts phone or cross-device transfer.

**YubiKey First-Class Support**:
- UI recognizes YubiKey AAGUIDs and displays model badge.
- All YubiKey transports supported: USB, USB-C, NFC.
- Documented setup flow: "Set up your YubiKey".

### Recovery Codes

- **Generation**: 10 single-use codes generated on first MFA enrollment (TOTP or WebAuthn).
- **Format**: Base64-url, ~12 chars each.
- **Storage**: Hash (SHA-256) persisted in DB.
- **Usage**: When TOTP device lost or WebAuthn key forgotten, user enters recovery code to regain access (audit-logged, flagged for follow-up).
- **Regeneration**: User can request new codes at any time; old codes are invalidated.

### MFA Policy

**Per-role enforcement**:

| Role | Default | Options |
|---|---|---|
| `owner` | `any` (TOTP or WebAuthn) | Recommend WebAuthn with attestation |
| `admin` | `any` (TOTP or WebAuthn) | Recommend WebAuthn with attestation |
| `operator` | Recommended | Optional, toggle in settings |
| `viewer` | Optional | Optional |

**Step-up MFA recency**: High-risk operations (secret reveal, role modification, host revoke) require fresh MFA ≤ 5 minutes (configurable, `FLEET_MFA_RECENCY_SECONDS`). If expired, user prompted for re-challenge.

---

## OIDC / OAuth 2.0

### Configuration

**Presets** (one-click setup, enabled by default):
- GitHub, GitLab, Google, Microsoft
- Authentik, Keycloak, Authelia
- Pocket ID, Zitadel
- Custom OIDC via discovery URL

**Setup flow**: Admin selects preset → enters Client ID/Secret → server auto-discovers endpoints (via `/.well-known/openid-configuration`) → tests connection → enables.

**Multi-provider**: Multiple OIDC providers can be active simultaneously. Users can link their account to any provider and use any of them to log in.

### Flow

1. **Authorization Code + PKCE only** (Implicit/Hybrid rejected).
2. **State + nonce validation**: State checked for CSRF; nonce verified in ID token.
3. **ID token signature verification**: JWKS cached 5 minutes; rotated on `kid` change.
4. **Claim extraction**:
   - `sub` (subject claim) → unique ID.
   - `email` → user email (required for email-based account linking).
   - Custom JSONPath for group/role extraction (configurable per provider).
5. **Account linking**: By email (with user confirmation) or admin-link. User's first OIDC login auto-creates local account; subsequent logins link to existing.
6. **JIT provisioning**: New user auto-created on first OIDC login (role-based on group claim or defaulting to `viewer`).

### MFA Integration

If upstream OIDC provider asserts MFA (via `acr` or `amr` claims), server honors it:
- Set local session `mfa_level = "external"`.
- Set `mfa_last_at = now()`.
- Avoids double-MFA on downstream step-up operations.

### Logout

- **RP-initiated** (where supported): Server sends user to provider's logout endpoint.
- **Fallback**: Local-only logout (clears session).
- **Session invalidation**: Logout always invalidates local session record.

### Steering UX

- **Setup wizard** lists 3 SSO presets first; local users buried under "Advanced".
- **Security posture**: Flags "local-password admins" as medium-risk with one-click "Migrate to SSO".
- **Login screen**: SSO buttons primary; "Local login" secondary.
- **Per-role enforcement**: Admin can set `sso_required=true` per role; login UI hides password field for matching email domains.

---

## API Keys

Recap from [Threat Model](../secure-dev/threat-model.md):

- **Format**: `hlk_` prefix + 32-byte base32 entropy. Last 4 characters stored plain for identification.
- **Scopes**: RBAC permission subset; user inherits only permissions ≤ their own.
- **IP allowlist**: Optional per-key; if set, requests from other IPs rejected.
- **Expiry**: Optional; can be indefinite or capped at user's role policy max.
- **Last-used tracking**: Logged in audit for security monitoring.
- **Rotation**: Instant create-new + revoke-old; UI walks user through.

---

## Secrets Broker (Session Integration)

The secrets broker is accessed by all auth components to store/retrieve sensitive data (TOTP secrets, OIDC client secrets, etc.). See [C3 Auth + Secrets Broker Design Spec](../../superpowers/specs/2026-05-02-hlh-c3-auth-secrets-design.md) for full details.

---

## Error Handling & Audit

All auth events are audit-logged (hash-chained):

| Event | Payload | Severity |
|---|---|---|
| `user.login_success` | `user_id`, `method` (local/oidc), `mfa_level`, `peer_ip` | info |
| `user.login_failed` | `email`, `reason`, `peer_ip`, `attempt_count` | warning |
| `user.mfa_challenge_failed` | `user_id`, `method`, `reason`, `peer_ip` | warning |
| `user.account_locked` | `user_id`, `locked_until`, `reason` (brute force) | warning |
| `user.password_reset` | `user_id`, `initiated_by` (user or admin) | info |
| `user.session_revoked` | `session_id`, `user_id`, `reason` | info |
| `user.mfa_enroll` | `user_id`, `method`, `device_name` | info |
| `user.mfa_revoke` | `user_id`, `method`, `device_name` | info |
| `oidc.account_linked` | `user_id`, `provider`, `provider_sub` | info |
| `oidc.jit_user_created` | `email`, `provider`, `role_assigned` | info |

---

## Related

- [Threat Model](../secure-dev/threat-model.md) — T8 (weak password), T10 (stolen session), T7 (bootstrap token)
- [C3 Auth + Secrets Broker Design Spec](../../superpowers/specs/2026-05-02-hlh-c3-auth-secrets-design.md) — Full implementation details
