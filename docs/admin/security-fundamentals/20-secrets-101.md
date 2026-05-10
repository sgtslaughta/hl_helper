---
title: Secrets 101
status: stable
---

# Secrets 101

A secret is anything that should not be public: passwords, API keys, database credentials, signing keys, or authentication tokens. This page covers what secrets are, why they matter, where they should (and should not) live, and how to rotate them safely.

## What Is a Secret?

A secret is any credential that grants access to a system. Examples:

- **Passwords**: SSH keys, admin passwords, database passwords
- **API keys**: GitHub tokens, cloud provider keys, third-party service credentials
- **Signing keys**: Keys used to sign commands, certificates, or audit logs
- **Tokens**: Session tokens, capability tokens, authorization bearer tokens

If an attacker gets a secret, they can impersonate the legitimate user or service. The impact ranges from minor (one container registry password) to catastrophic (the database master password or root signing key).

## Where Secrets Live (And Where They Don't)

### Don't Store Secrets Here

#### 1. In Source Code

Bad:

```python
# my_app.py
DB_PASSWORD = "mysecretpass123"
API_KEY = "sk-abc123def456"
```

Why it's bad:
- The secret is in version control history forever.
- Every developer, CI system, and automated scanner has access.
- If the repo is ever leaked (compromised account, public accident), the secret is public.

#### 2. In `.env` Files Committed to Git

Bad:

```
# .env (committed)
DATABASE_URL=postgres://user:password@localhost/db
```

Same problem as source code — it's in history.

#### 3. In Configuration Files That Ship in Containers

Bad:

```dockerfile
COPY config.yaml /app/config.yaml
# config.yaml contains the database password
```

When the container is pushed to a registry, the password is embedded in the image layers forever.

#### 4. In Logs

Bad:

```python
import logging
logger.info(f"Connecting to database with password: {password}")
```

Logs are often stored long-term, searched, and rotated to cold storage. A compromised log system exposes all your secrets.

#### 5. In Screenshots or Slack Messages

You take a screenshot of a command that includes an API key and post it to Slack. An attacker with access to Slack (or even publicly shared screenshots) now has the secret.

### Where Secrets Should Live

#### 1. Environment Variables at Runtime

Good:

```bash
export DB_PASSWORD="secret_value"
./myapp
```

The secret is only in memory, not on disk. Advantages:
- Process memory is ephemeral (lost on reboot).
- If the app crashes, the secret is not logged (if you exclude it from error handling).
- Easy to rotate without changing code.

Disadvantages:
- The secret is visible in `ps aux` output (solvable with process filtering).
- If the process is dumped in a debugger, the secret is visible.

#### 2. Files With Strict Permissions

Good:

```bash
chmod 0600 /etc/myapp/secrets.yaml
# Only the myapp user can read this file
```

Advantages:
- The file can be encrypted at rest.
- Permissions prevent unprivileged users from reading.
- Easy to audit file access.

Disadvantages:
- The file must be on disk somewhere.
- If the disk is stolen or the filesystem is mounted, the secret is exposed.

#### 3. A Secrets Manager (e.g., Vault)

Good: Using HashiCorp Vault, AWS Secrets Manager, or Azure Key Vault.

```python
from vault_client import VaultClient
vault = VaultClient(addr="https://vault.example.com")
secret = vault.read("secret/database/password")
```

Advantages:
- Secrets are never on disk in plaintext.
- Centralized audit log of who accessed what secret.
- Secrets can be rotated without redeploying code.
- Access can be revoked immediately.
- Encryption keys are managed separately.

Disadvantages:
- Adds operational complexity.
- Network dependency (Vault must be reachable).
- Initial setup takes time.

## Secret Rotation

Secrets age. If a secret is exposed, the sooner you know and rotate it, the smaller the window an attacker has.

### Why Rotate?

1. **Periodic rotation**: Even if you don't know of a breach, assume secrets might be leaked. Rotate them regularly (yearly, quarterly, or monthly depending on sensitivity).
2. **Incident response**: If you know a secret was exposed, rotate it immediately.
3. **Staff changes**: If someone with access leaves the organization, rotate secrets they could access.

### How Often?

- **Database master password**: Yearly or on staff change
- **API keys**: Yearly minimum; quarterly preferred
- **Signing keys**: Yearly minimum
- **Session tokens**: Already short-lived (hours to days)
- **Application credentials** (for connecting to services): Yearly or when discovered in logs

### The Rotation Process

Ideally, rotation is:

1. **Generate a new secret**: Create the new credential in the secrets manager.
2. **Deploy the new secret**: Update the application to use the new secret (while keeping the old one).
3. **Activate the new secret**: Switch the application to use the new secret.
4. **Verify**: Confirm the application is working with the new secret.
5. **Revoke the old secret**: Delete the old secret from the manager.

This avoids downtime. If step 3 fails, you roll back to step 2.

### Rotation Without Downtime

Some systems support multiple valid secrets at once:

- Database: Create a new user with the same privileges, activate it, then drop the old user.
- API keys: Generate a new key, configure the app to use it, then delete the old one (with a lag for in-flight requests).
- Signing keys: Publish both the old and new public keys; verifiers accept either. After a grace period, retire the old key.

hl_helper uses this pattern: the server's signing key rotates yearly, but both the old and new keys are trusted for 7 days during the transition.

## Least Privilege

A secret should only grant the minimum access needed.

### Example: Database

Bad:
```
DATABASE_URL=postgres://root:password@localhost/db
```
The app connects as root and can create/drop tables.

Good:
```
DATABASE_URL=postgres://app_user:password@localhost/db
# app_user has SELECT, INSERT, UPDATE on specific tables only
# app_user cannot DROP tables or TRUNCATE data
```

If the secret is compromised, the attacker is limited to what `app_user` can do.

### Example: API Keys

Bad:
```
GITHUB_TOKEN=ghp_abc123...
# Token has access to all repos in the account
```

Good:
```
GITHUB_TOKEN=ghp_xyz789...
# Token has read-only access to specific repos
# Token has an expiry (90 days)
```

### Example: Service Account

Bad:
```
AZURE_CREDENTIALS=credentials_with_all_permissions
```

Good:
```
AZURE_CREDENTIALS=credentials_with_only_storage_read_on_this_container
```

## Secrets and Containers

Containers make secret management tricky because:

1. Images are often public or shared across teams.
2. Secrets baked into the image are visible to anyone with access to the image.
3. Containers run as root by default in many setups.

Best practices:

- **Never bake secrets into images**: Use environment variables, mounted files, or external secret managers.
- **Use secrets-in-docker-compose or Kubernetes secrets**: These systems can inject secrets at runtime.
- **Encrypt the secret at rest**: If you must store it in a file, encrypt it with a key stored elsewhere.
- **Limit container access**: Don't run containers as root. Don't share `/var/lib/hl-agent/` between containers.

## Secrets in hl_helper

hl_helper stores several categories of secrets:

1. **Host signing keys**: Each agent's Ed25519 private key (used to sign command results).
2. **Server signing key**: The control plane's Ed25519 private key (used to sign commands).
3. **Intermediate CA key**: Used to sign host certificates (7-day TTL each).
4. **TLS private keys**: Host and server TLS keys.
5. **Database credentials**: Postgres password or SQLite file permissions.
6. **OIDC client secret** (if using external auth): For OpenID Connect login.

By default, hl_helper stores these on disk with file permissions (`mode 0600`) and optional encryption. The next page, [Vault Integration](./21-vault-integration.md), shows how to use a secrets manager for production deployments.

## Related Pages

- [Vault Integration](./21-vault-integration.md) — Using a secrets manager
- [Key Management](./key-management.md) — Protecting the most critical secrets
- [Design: Key Rotation](../../developer/design/key-rotation.md) — How keys rotate in hl_helper
