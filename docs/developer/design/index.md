---
title: Design Documentation
status: stable
---

# Design Documentation

This section documents the architectural and security design decisions underlying hl_helper's core subsystems. Each page covers the "why" and "how" of a critical component, grounded in the codebase and threat model.

## Pages

- **[Enrollment](enrollment.md)** — Host bootstrap: one-time token, CSR flow, internal CA signing, certificate constraints, re-enrollment policies
- **[Authentication](auth.md)** — User identity: local passwords (Argon2id), OIDC integration, MFA (TOTP + WebAuthn), sessions
- **[RBAC](rbac.md)** — Role-based access control: permission model, built-in roles, custom roles, capability tokens, Cedar extension
- **[Audit Chain](audit-chain.md)** — Tamper-evident logging: hash-chained entries, verification API, export formats, retention
- **[Key Rotation](key-rotation.md)** — TLS and signing key lifecycle: automatic rotation, recovery flows, compromise scenarios

All design decisions are informed by the [Threat Model](../secure-dev/threat-model.md) and cross-referenced with the [Agent Privilege Model](../secure-dev/agent-privilege-model.md).
