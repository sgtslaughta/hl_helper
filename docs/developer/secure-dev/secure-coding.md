---
title: Secure Coding
status: stable
---

# Secure Coding

Practices for writing hl_helper code safely: input validation, subprocess handling, secrets management, cryptography, logging, error handling, file I/O, concurrency, and examples.

---

## Input Validation

**Boundary enforcement**: Validation occurs at all ingress points — API endpoints, gRPC handlers, CLI arguments, and agent-reported data.

### API and gRPC Endpoints

All inputs are validated via Pydantic v2 models. Do not trust user input or agent-reported strings without bounds:

**Good:**
```python
from pydantic import BaseModel, Field, constr

class CommandRequest(BaseModel):
    host_id: str = Field(..., regex="^[a-z0-9-]+$", max_length=255)
    command: constr(max_length=10000) = None  # max 10KB
    timeout_sec: int = Field(ge=1, le=3600)  # 1s to 1h only
```

**Bad:**
```python
# Unconstrained input — can be huge, contain special chars
async def run_cmd(host_id: str, command: str):
    pass
```

### Agent-Reported Strings

Metrics from the agent (hostname, OS version, metrics) are not trusted for display or decision-making without normalization:

**Good:**
```python
# Sanitize agent-reported hostname before logging
hostname_normalized = host_metrics.hostname.strip()[:255].encode("utf-8", errors="replace").decode()
audit_log.info(f"host_online hostname={hostname_normalized}")
```

**Bad:**
```python
# Direct use of agent data — may contain newlines, ANSI codes, injection
audit_log.info(f"host_online hostname={host_metrics.hostname}")
```

### Schema Validation for Protobuf

gRPC messages are schema-validated at the protoc layer. Before processing, re-validate semantic constraints:

**Good:**
```python
# Verify manifest signature before trusting its content
manifest_sig_valid = verify_ed25519(
    manifest.signature,
    manifest_bytes,
    server_pubkey
)
if not manifest_sig_valid:
    raise PermissionDenied("manifest signature invalid")
# Now safe to use manifest.allowed_actions
```

**Bad:**
```python
# Trust manifest without signature check
allowed_actions = manifest.allowed_actions  # UNSAFE
```

---

## Subprocess Execution

**Rules**: List-based args only, never `shell=True`, no string interpolation of user input into command strings.

### Good: List Args

```python
import subprocess

# Safe: args as list, no shell
result = subprocess.run(
    ["/usr/bin/apt-get", "install", package_name],
    capture_output=True,
    timeout=300
)
```

### Bad: Shell Interpolation

```python
# UNSAFE: shell=True + interpolation
subprocess.run(
    f"apt-get install {package_name}",
    shell=True  # DO NOT DO THIS
)

# UNSAFE: string concatenation
subprocess.run(
    "/usr/bin/apt-get install " + package_name,
    # ...
)
```

### Sudoers Allowlist

Commands requiring root are run via `sudo`. The sudoers allowlist (per-distro) enforces which binaries and args can be used. Agent code must use the exact paths and args defined in the allowlist:

```python
# Deploy-time sudoers.d/hl-agent.deb:
# hl-agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get install *

# At runtime, agent calls:
subprocess.run(["/usr/bin/apt-get", "install", package_name], ...)
```

Never execute arbitrary paths or deviate from the allowlist. Sudoers is the second layer of defense (first is the agent manifest).

---

## SQL: ORM Only

**Rule**: Use SQLAlchemy 2.x ORM exclusively. Never write raw SQL, never f-string queries.

### Good: ORM with Type Safety

```python
from sqlalchemy.orm import Session
from server.app.models import Host

async def get_host(session: Session, host_id: str) -> Host:
    # Type-safe, parameterized query
    return await session.scalar(
        select(Host).where(Host.id == host_id)
    )
```

### Bad: Raw SQL (DO NOT USE)

```python
# UNSAFE: SQL injection risk, even with .format()
query = f"SELECT * FROM hosts WHERE id = '{host_id}'"
session.execute(query)

# UNSAFE: .format() is not parametric
query = "SELECT * FROM hosts WHERE id = {}".format(host_id)
```

Even `%s` substitution is risky if misused. Always use the ORM.

---

## Secrets Management

**Rules**: Secrets (API keys, signing keys, credentials) come from Vault or environment variables at startup. Never store literals. Always redact in logs. Use constant-time comparison for tokens.

### Loading Secrets at Startup

```python
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Load from env; no default
    vault_token: str = os.environ["FLEET_VAULT_TOKEN"]
    db_password: str = os.environ["FLEET_DB_PASSWORD"]
    
    # Optional, falls back to default (not a secret)
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")

# Load once at startup, pass around as dependency
settings = Settings()
```

### Redaction in Logs

```python
import structlog

# Good: explicitly redact sensitive fields
audit_log.info(
    "enrollment_token_issued",
    token="<redacted>",  # Do not log the actual token
    host_id=host_id,
)

# Good: use a filter to redact patterns
def redact_secrets(logger, method_name, event_dict):
    for key in ["password", "token", "secret", "key"]:
        if key in event_dict:
            event_dict[key] = "<redacted>"
    return event_dict

# Add filter to all loggers
structlog.configure(
    processors=[
        redact_secrets,
        structlog.processors.JSONRenderer(),
    ]
)
```

### Constant-Time Token Comparison

```python
import hmac

# Good: constant-time comparison
def verify_session_token(provided: str, stored_hash: bytes) -> bool:
    computed = hmac.new(stored_hash, provided.encode(), "sha256").digest()
    return hmac.compare_digest(computed, stored_hash)

# Bad: == operator leaks timing info
if provided_token == actual_token:  # DO NOT USE FOR TOKENS
    pass
```

---

## Cryptography: Ed25519 and ECDSA

**Rules**: Use only `cryptography` library. Never roll custom crypto. Key sizes: Ed25519 (32 bytes signing), ECDSA P-256 (TLS certs).

### Ed25519 Signing

```python
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend

# Load signing key from file
with open("/var/lib/hl-agent/signing.key", "rb") as f:
    private_key = serialization.load_pem_private_key(
        f.read(),
        password=None,
        backend=default_backend()
    )

# Sign a message
message = b"command payload"
signature = private_key.sign(message)

# Verify signature (agent-side, given server's public key)
from cryptography.exceptions import InvalidSignature
try:
    server_pubkey.verify(signature, message)
    print("Valid")
except InvalidSignature:
    print("Invalid signature")
```

### ECDSA P-256 (TLS Certs)

```python
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography import x509
from cryptography.x509.oid import NameOID

# Generate key
private_key = ec.generate_private_key(ec.SECP256R1())

# Create cert (handled by CA at enrollment; agent just stores/uses)
# See docs/developer/architecture/transport.md for cert details
```

---

## Argon2id Password Hashing

**Configuration**: Hash admin passwords with Argon2id (not bcrypt). Settings from `docs/developer/design/auth.md`:

```python
from argon2 import PasswordHasher

hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Hash
password_hash = hasher.hash("user_password")

# Verify
try:
    hasher.verify(password_hash, provided_password)
except VerifyMismatchError:
    raise Unauthorized("Invalid password")
```

Enforce password complexity with zxcvbn; optionally check against HIBP (Have I Been Pwned). See `docs/developer/design/auth.md` for full auth flow.

---

## Logging: Structured, No PII

**Rules**: Use JSON-based structured logging. Never log secrets, passwords, PII, or stack traces to the client.

### Structured Logging

```python
import structlog

# Configure at startup
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()

# Log with context
log.info(
    "command_executed",
    command_id="abc123",
    host_id="host-xyz",
    exit_code=0,
    # Do NOT log stdout/stderr if large or sensitive
)
```

### PII and Path Redaction

```python
# Redact absolute paths above $HOME
home = os.path.expanduser("~")
def redact_path(path):
    if path.startswith(home):
        return path.replace(home, "$HOME")
    return path  # system paths are OK to log

log.info("file_operation", path=redact_path("/home/user/.ssh/id_rsa"))
# Output: path=$HOME/.ssh/id_rsa
```

---

## Error Handling: Never Leak Stack Traces

**Rules**: Catch broad exceptions, log internally, return generic errors to clients.

### Good: Catch-Log-Return Pattern

```python
from fastapi import HTTPException
import traceback

@app.post("/api/v1/command")
async def run_command(req: CommandRequest) -> CommandResponse:
    try:
        # Business logic
        result = await executor.run(req.command, req.host_id)
        return CommandResponse(success=True, result=result)
    except HostOfflineError:
        # Known, safe error — can return details
        raise HTTPException(status_code=503, detail="Host offline")
    except Exception as e:
        # Unknown error — log internally, return generic
        log.error("command_execution_error", error=str(e))
        log.debug("traceback", traceback=traceback.format_exc())  # debug level only
        raise HTTPException(
            status_code=500,
            detail="Internal server error"  # Safe generic message
        )
```

### Bad: Leak Stack Traces

```python
@app.post("/api/v1/command")
async def run_command(req: CommandRequest):
    # If exception not caught, FastAPI returns full traceback to client
    # UNSAFE: attacker learns internals, file paths, versions
    result = await executor.run(req.command, req.host_id)
    return result
```

---

## File Operations: Path Validation

**Rules**: Validate paths against an allowlist. No `..` traversal. Use `pathlib.Path.resolve()` and `is_relative_to()`.

### Good: Validate Against Allowlist

```python
from pathlib import Path

ALLOWED_DIRS = [
    Path("/var/lib/hl-agent"),
    Path("/etc/hl-agent"),
]

def safe_read_file(filename: str) -> bytes:
    # Resolve to absolute path
    requested = Path(filename).resolve()
    
    # Check if it's under an allowed directory
    for allowed_dir in ALLOWED_DIRS:
        try:
            requested.relative_to(allowed_dir)
            # Falls through only if requested is under allowed_dir
            return requested.read_bytes()
        except ValueError:
            # Not relative to this allowed_dir
            continue
    
    raise PermissionError(f"{filename} is not in allowed directories")
```

### Bad: No Validation

```python
def read_file(filename: str) -> bytes:
    # UNSAFE: attacker can use "../../../etc/shadow"
    return Path(filename).read_bytes()
```

---

## Concurrency: Asyncio and Explicit Locks

**Rules**: Prefer asyncio (async/await) over threads. Use explicit locks for shared mutable state. SQLAlchemy 2.x integrates with asyncio.

### Good: Async Concurrency

```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

async def process_batch(host_ids: list[str]):
    """Process hosts concurrently"""
    tasks = [process_host(hid) for hid in host_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

async def process_host(host_id: str):
    async with session() as db:
        host = await db.scalar(select(Host).where(Host.id == host_id))
        # ...
```

### Explicit Locks for Shared State

```python
import asyncio

class Registry:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._data = {}
    
    async def add(self, key, value):
        async with self._lock:
            self._data[key] = value
    
    async def get(self, key):
        async with self._lock:
            return self._data.get(key)
```

---

## Code Examples

### Full Secure Flow: Enroll Agent

```python
# This is pseudocode; see actual implementation in server/app/api/v1/enrollment_tokens.py

@app.post("/v1/enroll")
async def enroll_agent(req: EnrollmentRequest, session: AsyncSession) -> EnrollmentResponse:
    """
    Secure enrollment: validate token, check rate limit, issue cert, mark token consumed.
    """
    # 1. Validate request schema (Pydantic)
    assert len(req.token) <= 256
    assert len(req.csr_pem) <= 10000
    
    # 2. Rate limit: per-IP, 5 burst + 0.5/s sustained
    ip = request.client.host
    if not await rate_limiter.check("enroll", ip):
        raise HTTPException(status_code=429, detail="Too many requests")
    
    # 3. Look up token (parameterized query via ORM)
    token_record = await session.scalar(
        select(HostToken).where(
            HostToken.token_hash == hash_token(req.token)
        )
    )
    
    if not token_record or token_record.redeemed_at:
        # Token invalid or already used
        log.warning("enrollment_token_invalid", ip=ip)  # Safe to log
        raise HTTPException(status_code=410, detail="Token invalid or expired")
    
    if token_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Token expired")
    
    # 4. Validate CSR (check schema only; signature verified after cert generation)
    try:
        csr = x509.load_pem_x509_csr(req.csr_pem.encode(), default_backend())
    except Exception as e:
        log.warning("enrollment_csr_invalid", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid CSR")
    
    # 5. Generate host ID and cert
    host_id = generate_host_id()
    cert = sign_csr(csr, host_id, ca_key, validity_days=1)
    
    # 6. Atomically mark token consumed and create host
    try:
        token_record.redeemed_at = datetime.utcnow()
        new_host = Host(
            id=host_id,
            hostname=req.hostname[:255],
            agent_pubkey=req.agent_pubkey,
        )
        session.add(new_host)
        await session.commit()
    except Exception as e:
        await session.rollback()
        log.error("enrollment_commit_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Enrollment failed")
    
    # 7. Log enrollment (no secrets)
    log.info("host_enrolled", host_id=host_id, ip=ip)
    
    # 8. Return cert chain
    return EnrollmentResponse(
        host_id=host_id,
        cert_chain_pem=cert_to_pem(cert),
        ca_chain_pem=ca_chain,
        grpc_endpoint=f"{FLEET_GRPC_ENDPOINT}:443",
    )
```

---

## References

- **Threat Model**: `docs/developer/secure-dev/threat-model.md`
- **Authentication**: `docs/developer/design/auth.md` (Argon2id, MFA, sessions)
- **Transport**: `docs/developer/architecture/transport.md` (signing, mTLS, replay)
- **Agent Privilege Model**: `docs/developer/secure-dev/agent-privilege-model.md`
- **RBAC**: `docs/developer/design/rbac.md`
