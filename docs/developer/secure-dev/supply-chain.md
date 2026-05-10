---
title: Supply Chain Security
status: stable
---

# Supply Chain Security

Dependency pinning, SBOM, signed releases, plugin verification, build provenance, vulnerability response, and dependency review practices.

---

## Dependency Pinning

**Python**: Dependencies are pinned in `pyproject.toml` with exact version ranges and verified via `uv.lock` lockfile. All updates are reviewed before merge.

### pyproject.toml Version Ranges

```toml
[project]
dependencies = [
  "fastapi>=0.115",        # >= version, SemVer constraint
  "cryptography>=44",      # >= version, SemVer constraint
  "pydantic>=2.9",         # >= version, SemVer constraint
  "sqlalchemy>=2.0",       # >= version; 2.x is required for type safety
]
```

All critical security libraries (cryptography, pydantic, sqlalchemy, grpcio) are pinned to major versions. Patch updates are automatically bundled by `uv` and reviewed monthly.

### Lockfile: uv.lock

Generated via `uv lock` after updating dependencies:

```bash
uv lock  # Updates uv.lock with all transitive deps
git diff uv.lock  # Review before commit
```

The `uv.lock` file is committed to git and ensures reproducible installs across environments.

### Node.js / Web UI

Dependencies are pinned in `package-lock.json` (or `pnpm-lock.yaml` if using pnpm). Update via:

```bash
npm install
# or
pnpm install
```

Commit the lockfile to git.

---

## Software Bill of Materials (SBOM)

**Python**: SBOM generation is via `cyclonedx-py` (optional, for compliance/audit).

### Generating Python SBOM

```bash
pip install cyclonedx-bom
cyclonedx-py --output-format json --output sbom.json .
```

Output: CycloneDX-compliant JSON with all transitive dependencies, versions, and known CVEs.

### Node.js SBOM (Planned)

```bash
npm install -g @cyclonedx/npm
cyclonedx-npm --output-file sbom.json
```

**Status**: SBOM generation is planned for the next release. Not yet integrated into the CI pipeline.

### Agent Binary SBOM

The Go agent binary (built with `go build`) is scanned with:

```bash
go install github.com/CycloneDX/cyclonedx-gomod/cmd/cyclonedx-gomod@latest
cyclonedx-gomod -output sbom.json
```

Included in signed release artifacts.

---

## Signed Releases

**Agent Binary Signing**: Agent binaries are signed with cosign (post-v1.0 planned).

### Cosign Setup (Planned)

```bash
# Generate keys (one-time, stored offline)
cosign generate-key-pair

# Sign binary release
cosign sign-blob \
  --key cosign.key \
  --tlog-upload=true \
  hl-agent-amd64

# Verify signature
cosign verify-blob \
  --key cosign.pub \
  --signature hl-agent-amd64.sig \
  hl-agent-amd64
```

**Current Status**: v1.0 releases are unsigned. Cosign integration is planned for **v1 GA** (post-May 2026).

### Release Checksums

All releases include SHA256 checksums:

```bash
sha256sum hl-agent-* > checksums.txt
gpg --sign checksums.txt  # Sign checksums (admin-only key)
```

---

## Plugin Verification

Plugins are signed OCI artifacts. At load time, the agent verifies cosign signatures before executing any plugin.

### Plugin Manifest Structure

```json
{
  "name": "example-plugin",
  "version": "1.0.0",
  "image": "ghcr.io/example/plugin:latest",
  "signature": "<cosign signature>",
  "capabilities": ["docker_exec", "systemctl_control"],
  "secrets_required": ["REGISTRY_AUTH"],
  "sandbox": "bwrap"
}
```

### Plugin Signature Verification (Agent-Side)

```python
# Agent code: before loading plugin, verify signature
result = subprocess.run([
    "cosign", "verify-blob",
    "--key", "/etc/hl-agent/plugin-pubkeys.txt",
    "--signature", plugin_manifest.signature,
    plugin_manifest.image
], check=False)

if result.returncode != 0:
    raise PluginVerificationFailed(f"Plugin {plugin_manifest.name} signature invalid")

# Only after verification: load and run plugin
plugin = load_plugin_oci(plugin_manifest.image)
```

**Full Details**: See `docs/developer/secure-dev/agent-privilege-model.md` (Plugin Sandbox Model section).

---

## Dependabot / Renovate

**Status**: Dependabot is enabled on the GitHub repository for Python and Node.js dependencies.

### Configuration

File: `.github/dependabot.yml`

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
      day: monday
      time: "03:00"
    open-pull-requests-limit: 5
    reviewers: ["sgtslaughta"]
    labels: ["dependencies", "review-soon"]
    commit-message:
      prefix: "chore(deps):"

  - package-ecosystem: npm
    directory: "/webui"
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels: ["dependencies", "review-soon"]

  - package-ecosystem: gomod
    directory: "/agent"
    schedule:
      interval: weekly
    labels: ["dependencies", "review-soon"]
```

**Cadence**: Weekly checks on Mondays. Security fixes are prioritized (auto-merge for patch versions of critical libs like cryptography, sqlalchemy).

---

## Lockfile Review: PR Template

Every PR that modifies dependencies includes a summary. The PR template enforces this:

```markdown
## Dependency Changes

- [ ] No lockfile changes, OR
- [ ] Lockfile changes reviewed (list below)

**uv.lock changes**:
- [Dependency Name] X.Y.Z → X.Y.Z' (reason: security patch / feature / compliance)

**package-lock.json changes**:
- [Package Name] X.Y.Z → X.Y.Z' (reason)
```

**Reviewer checklist**:
- [ ] Verify all transitive dependencies are from trusted sources.
- [ ] Check if any dependency was recently compromised (search CVE lists).
- [ ] Confirm version bumps are necessary (don't upgrade just because a new version exists).

---

## Build Provenance (SLSA Level)

**Planned for post-v1.0**. Currently, releases are built on GitHub Actions without cryptographic provenance.

### Future: SLSA Level 2 / 3

Once implemented:

```bash
# Provenance file is generated by GitHub Actions
# Example: hl-agent-amd64.intoto.jsonl (In-Toto attestation)

# Verify provenance
slsa-verifier verify-artifact hl-agent-amd64 \
  --provenance hl-agent-amd64.intoto.jsonl \
  --source-uri github.com/yourusername/hl_helper
```

**Status**: SLSA provenance generation is planned for the next release.

---

## Vulnerability Response

All contributors, users, and third parties must follow this process for reporting and handling security vulnerabilities.

### Reporting a Vulnerability

1. **Do not open a public issue**. Instead, email `security@hl-helper.local` (or create a private security advisory on GitHub).
2. **Include**: Affected version(s), component, CVE (if known), proof-of-concept (if safe to share), and proposed mitigation.
3. **Expect acknowledgment within 24 hours** (SLA: 48 hours for non-critical issues).

### Triage and Response

| Severity | Response Time | Action |
|---|---|---|
| **Critical** (RCE, auth bypass) | < 4 hours | Issue hotfix release, notify all users |
| **High** (privilege escalation, confidentiality) | < 24 hours | Issue patch release within 7 days |
| **Medium** (DoS, info leakage) | < 2 days | Include in next regular release |
| **Low** (linting, non-security UX) | < 7 days | Include in next regular release |

### Patch Release Process

1. Create a private branch for the fix (do not commit to main).
2. Write unit + integration tests to verify the fix.
3. Review with security team (or designated senior engineer).
4. Merge to a release branch (`release/vX.Y.Z`).
5. Tag and publish: `git tag -s v0.1.1 -m "Security patch: ..."`.
6. Draft release notes highlighting the CVE and fix.
7. Publish to GitHub Releases and npm/PyPI.
8. Announce via security mailing list (if one is established).

### CVE Disclosure

Once a fix is released, we request a CVE ID from MITRE (optional but recommended for critical issues). The CVE is published in the release notes.

---

## Upstream Dependencies: Vulnerability Monitoring

### GitHub Dependabot Alerts

GitHub automatically scans dependencies and creates alerts for known CVEs. Dependabot PRs are created automatically for patches.

**Workflow**:
1. Dependabot detects a CVE in a dependency.
2. Creates a PR with the upgrade.
3. CI pipeline runs (tests, linting, docs).
4. Reviewer approves (within 24 hours for critical CVEs).
5. Merge and release hotfix if necessary.

### Manual CVE Checks

Monthly, a designated maintainer runs:

```bash
pip install safety
safety check --json > cve-report.json

# or use Snyk
snyk test --file=pyproject.toml
```

And reviews the report for any undetected vulnerabilities.

---

## Vendoring (Not Used)

hl_helper does **not** vendor dependencies. All dependencies are fetched from PyPI, npm, and go.pkg.dev at build time. This ensures we receive upstream security patches immediately.

**Exception**: Protobuf-generated code (`server/app/grpc/_pb/`) is generated from `.proto` definitions (not vendored; excluded from linting).

---

## CI/CD Security Checks

The `docs.yml` and `ci.yml` workflows enforce security checks on every PR:

1. **Dependency check** (Dependabot audit): Fail if high-severity CVEs are introduced.
2. **Lint** (ruff, mypy): Code quality and type safety.
3. **Test** (pytest, go test): Functional correctness.
4. **Docs** (pytest tests/docs/, lychee link check): Documentation validity.

If any check fails, the PR cannot be merged (branch protection rules).

---

## Reproducible Builds

Python packages are built from source via `pip install -e ".[dev]"` (editable mode for local development). Production releases will use wheel distributions.

**Future**: Implement reproducible wheel builds via [build](https://pypa-build.readthedocs.io/) and PEP 427 (standard wheel format).

---

## References

- **Threat Model**: `docs/developer/secure-dev/threat-model.md` (T2 supply-chain attacks)
- **Agent Privilege Model**: `docs/developer/secure-dev/agent-privilege-model.md` (Plugin verification)
- **Transport**: `docs/developer/architecture/transport.md` (signed commands, cosign)
- **Dependabot Docs**: https://docs.github.com/en/code-security/dependabot
- **CycloneDX**: https://cyclonedx.org/
- **Cosign**: https://docs.sigstore.dev/cosign/
- **SLSA**: https://slsa.dev/ (build provenance framework)
