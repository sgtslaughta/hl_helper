---
title: Security Fundamentals
status: stable
---

# Security Fundamentals

A learning ladder from "why does this matter?" to operating a hardened deployment. This guide is written for self-hosting hobbyists, sysadmins, and homelab operators who want to understand the security decisions in hl_helper and how to operate it safely.

## The Ladder

Read in order. Pairs (even-numbered concept page ↔ odd-numbered concrete page) follow this pattern: learn the concept first, then see how hl_helper implements it.

1. **[Why security matters](./00-why-security.md)** — Why a homelab management tool needs security
2. **[TLS basics](./10-tls-basics.md)** → **[mTLS in hl_helper](./11-mtls-in-hlhelper.md)** — Encryption and peer authentication
3. **[Secrets 101](./20-secrets-101.md)** → **[Vault integration](./21-vault-integration.md)** — Where secrets live and how to rotate them
4. **[RBAC basics](./30-rbac-basics.md)** → **[Cedar policies](./31-cedar-policies.md)** — Access control: who can do what
5. **[Incident response](./40-incident-response.md)** → **[Runbooks](./41-runbooks.md)** — What to do when something breaks

## Companion Pages

These live in the same directory; start with the ladder first.

- **[Enrollment](./enrollment.md)** — How hosts securely join your fleet for the first time
- **[Key management](./key-management.md)** — Protecting the keys that protect everything else

## Where This Fits

- **For operators**: Start here to understand what you're defending, then read the companion pages.
- **For self-hosters**: Use this + the runbooks when things go wrong.
- **For developers**: This is the user-facing security story; see `docs/developer/` for architectural details.

## A Quick Note

This ladder assumes you:
- Can SSH into your own machines
- Know what "a certificate" is (we explain the rest)
- Are comfortable reading configuration files

It does not assume cryptography knowledge — we keep it practical, not academic.
