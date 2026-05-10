---
title: Vault Integration
status: partial
---

# Vault Integration

This page shows how to integrate hl_helper with HashiCorp Vault for production secret management. Using Vault moves secrets off disk and into a centralized system with encryption, audit logging, and fine-grained access control.

## When to Use Vault

You should integrate Vault if:
- You run multiple instances of hl_helper (Vault holds a single copy of secrets, all instances read from it).
- You have compliance requirements (audit logs, encryption key management).
- You want to rotate secrets without redeploying code.
- You want to revoke access instantly if someone leaves.

You can skip Vault if:
- You run a single hl_helper instance in a homelab.
- You're okay with secrets-on-disk with restrictive file permissions.
- You're not subject to compliance regulations.

## Architecture

With Vault:

```
hl_helper server
    ↓ (on startup, authenticate)
Vault
    ↓ (on auth success, receive signed token)
hl_helper server
    ↓ (use token to read secrets)
Vault → secret value
```

Secrets never pass through hl_helper's filesystem. The server authenticates to Vault once, receives a short-lived token, and uses it to read secrets on-demand.

## Installation and Setup

### Step 1: Install Vault

On your Vault server (separate machine, not the hl_helper server):

```bash
# Download Vault from https://www.vaultproject.io/downloads
# Or use a package manager
sudo apt-get install vault

# Start Vault (development mode for testing; use integrated storage or Consul for production)
vault server -dev

# In another terminal, set environment variable
export VAULT_ADDR="http://localhost:8200"
export VAULT_TOKEN="<from startup output>"

# Verify
vault status
```

For production, use integrated storage (Raft) or external storage (Consul, S3, etc.). See [Vault deployment guide](https://www.vaultproject.io/docs/concepts/integrated-storage) for details. This page assumes Vault is running and unsealed.

### Step 2: Create an AppRole for hl_helper

AppRole is a Vault authentication method that is ideal for applications:

```bash
# Enable AppRole auth method
vault auth enable approle

# Create a role for hl_helper
vault write auth/approle/role/hlhelper-server \
  token_ttl=1h \
  token_max_ttl=24h \
  policies="hlhelper-server"

# Get the role ID
vault read auth/approle/role/hlhelper-server/role-id
# Output: role_id = abc123

# Generate a secret ID (one-time use)
vault write -f auth/approle/role/hlhelper-server/secret-id
# Output: secret_id = xyz789
```

Keep the role ID and secret ID safe. The secret ID can be used only once to authenticate.

### Step 3: Create the Secret Policy

Define what secrets hl_helper can read:

```bash
# Create a policy file
cat > /tmp/hlhelper-server.hcl << 'EOF'
# Read hl_helper secrets
path "secret/data/hlhelper/*" {
  capabilities = ["read", "list"]
}

# Read database credentials
path "secret/data/database/hlhelper" {
  capabilities = ["read"]
}

# Rotate signing keys (if using Vault's pki engine)
path "pki/sign/hlhelper-server" {
  capabilities = ["create", "update"]
}
EOF

vault policy write hlhelper-server /tmp/hlhelper-server.hcl
```

This policy allows hl_helper to read secrets under `secret/data/hlhelper/` and `secret/data/database/hlhelper`, and to request certificate signing.

### Step 4: Store Secrets in Vault

Encrypt and store your hl_helper secrets in Vault:

```bash
# Server signing key (export from hl_helper first)
vault kv put secret/hlhelper/signing-key \
  private_key="@/path/to/signing.key" \
  rotation_schedule="yearly"

# Database password
vault kv put secret/database/hlhelper \
  username="hlhelper_user" \
  password="<strong-password>"

# OIDC client secret (if using OIDC)
vault kv put secret/hlhelper/oidc \
  client_id="..." \
  client_secret="..."
```

## Configuring hl_helper to Use Vault

Set environment variables on the hl_helper server:

```bash
# Vault connection
export VAULT_ADDR="https://vault.example.com:8200"
export VAULT_SKIP_VERIFY=false  # verify TLS cert (set to true only for testing)

# AppRole authentication
export VAULT_ROLE_ID="abc123"
export VAULT_SECRET_ID="xyz789"

# Secret paths (tell hl_helper where to find secrets)
export HL_VAULT_ENABLED=true
export HL_VAULT_SIGNING_KEY_PATH="secret/data/hlhelper/signing-key"
export HL_VAULT_DB_CREDS_PATH="secret/data/database/hlhelper"
export HL_VAULT_OIDC_PATH="secret/data/hlhelper/oidc"

# Start hl_helper
./hl-helper server
```

On startup, hl_helper will:

1. Authenticate using AppRole (role ID + secret ID).
2. Receive a token valid for 1 hour.
3. Use the token to read `HL_VAULT_SIGNING_KEY_PATH`, `HL_VAULT_DB_CREDS_PATH`, etc.
4. Store these values in memory (not on disk).
5. Before the token expires, automatically refresh by re-authenticating.

## Secret Rotation With Vault

Vault handles rotation transparently:

### Rotate the Server Signing Key

1. In Vault, generate a new signing key:
   ```bash
   vault kv put secret/hlhelper/signing-key \
     private_key="@/path/to/new-signing.key" \
     rotation_schedule="yearly"
   ```

2. hl_helper automatically detects the change on the next token refresh (within 1 hour).

3. New commands use the new signing key. Old commands signed with the old key are still valid for 7 days (grace window).

### Rotate the Database Password

1. In your database, change the password:
   ```sql
   ALTER USER hlhelper_user WITH PASSWORD 'new-password';
   ```

2. Update Vault:
   ```bash
   vault kv put secret/database/hlhelper \
     username="hlhelper_user" \
     password="new-password"
   ```

3. hl_helper picks up the new password on the next connection attempt (within 1 hour). Existing connections are not affected until the next reconnect.

## Advanced: PKI Secret Engine (Planned)

In a future version, hl_helper can use Vault's PKI secret engine to generate host certificates on-demand:

```bash
# (Planned, not yet shipped)
vault write pki/issue/hlhelper-host \
  common_name="spiffe://hl_helper/host/abc123"
```

This eliminates the need to run an internal CA on the server — Vault becomes the CA. This is marked as **planned** because it's not yet integrated.

## Monitoring and Troubleshooting

### Health Check

Verify Vault connectivity:

```bash
curl -H "X-Vault-Token: $VAULT_TOKEN" https://vault.example.com:8200/v1/sys/health
```

### Audit Logs

All secret reads are logged in Vault:

```bash
vault audit list
# Output: file    file    /var/log/vault/audit.log

# Check the audit log
tail /var/log/vault/audit.log | jq .
```

You'll see entries like:

```json
{
  "auth": {
    "client_token": "hvs.abc123...",
    "display_name": "approle"
  },
  "request": {
    "path": "secret/data/hlhelper/signing-key",
    "operation": "read"
  },
  "response": {
    "data": { ... }
  }
}
```

### Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `permission denied` when reading secret | Policy doesn't allow it | Update the policy (`vault policy write hlhelper-server ...`). |
| `secret not found` | Secret not stored in Vault yet | Store it: `vault kv put secret/hlhelper/...`. |
| `token expired` | hl_helper didn't refresh in time | Restart hl_helper to re-authenticate. Increase token TTL if needed. |
| TLS cert verification failed | `VAULT_SKIP_VERIFY=true` but connecting to wrong hostname | Ensure `VAULT_ADDR` matches the cert CN. |

## File-Based Fallback

If Vault is unavailable, hl_helper can fall back to file-based secrets (on-disk with mode 0600):

```bash
export HL_VAULT_ENABLED=false
export HL_SECRETS_DIR="/var/lib/hl-helper/secrets"

# Secrets on disk
ls /var/lib/hl-helper/secrets/
# - signing.key
# - db-password
```

This is useful for:
- Development and testing.
- Single-instance homelabs.
- Disaster recovery (Vault is down, but hl_helper must keep running).

## Security Considerations

### Vault Security

- **Seal key**: The seal key is the master key. Store it offline, encrypted. Never put it in version control.
- **TLS cert for Vault**: Use a valid TLS certificate (not self-signed) so hl_helper can verify Vault is legitimate.
- **Admin token**: Don't use the root token in production. Create limited-privilege tokens for each service.

### Secret ID Rotation

The secret ID used for AppRole authentication is one-time use. After it's used, Vault invalidates it. To rotate the credentials:

1. Generate a new secret ID:
   ```bash
   vault write -f auth/approle/role/hlhelper-server/secret-id
   ```

2. Update the environment variable on the hl_helper server:
   ```bash
   export VAULT_SECRET_ID="new-secret-id"
   ./hl-helper server
   ```

3. Verify hl_helper connects successfully.

4. The old secret ID is now useless (can't be reused).

## Related Pages

- [Secrets 101](./20-secrets-101.md) — Why secrets matter
- [Key Management](./key-management.md) — Protecting keys offline
- [Design: Key Rotation](../../developer/design/key-rotation.md) — How keys rotate
- [Vault Documentation](https://www.vaultproject.io/docs) — Full Vault guide
