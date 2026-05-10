---
title: Why Security Matters
status: stable
---

# Why Security Matters

You're running machines at home — routers, NAS boxes, lab servers, maybe a Kubernetes cluster on old laptops. hl_helper helps you manage them. But why does a homelab tool need security at all? This page explains the threat landscape in language that makes sense for hobbyists, not enterprises.

## The Threat Landscape

### Opportunistic Scanning

The internet is constantly scanned. Shodan, Censys, and random botnets probe IP addresses looking for open ports, weak credentials, and known vulnerabilities. If you expose a management interface on a non-standard port hoping no one finds it, you're playing "security by obscurity" — and it doesn't work.

**What happens**: An attacker runs an automated scan, finds your management interface, guesses a password, and gains shell access to your machines.

**Why hl_helper helps**: mTLS (mutual TLS) means even if the port is discovered, attackers can't connect without a valid certificate. Passwords are one piece; cryptographic proof is another.

### Supply-Chain Compromise

You install a Linux package, a Go binary, or a Python library. One of those dependencies has 50 transitive dependencies. One of *those* dependencies gets hijacked — the maintainer's account is compromised, or they sell the project to someone with malicious intent.

**What happens**: The infected package sits in your system, waiting. It might exfiltrate credentials, report your IP to a botnet, or forward commands from an attacker.

**Why hl_helper helps**: Every command from the control plane is signed. Every response from an agent is signed. Even if a dependency is compromised and tries to run unapproved commands, signatures will fail and the audit trail will show it.

### Credential Theft

A password is stored in a config file, a .env file, or a screenshot. An attacker gains read access to one machine in your fleet (maybe through a container escape, a kernel bug, or a plugin exploit). They find the password and use it to access all your other machines.

**What happens**: One compromised host becomes a pivot point to compromise everything else.

**Why hl_helper helps**: Secrets are separated from the code and configuration. If one host is compromised, the attacker gains only that host's keys — not the master signing key or admin credentials. Revocation procedures let you remove that host from your fleet within minutes.

### Lateral Movement

Your router is compromised. An attacker on that router sees all unencrypted traffic between your machines. They watch your management tool sending commands, capture the command, and replay it (run the same backup command 10 times, or corrupt the database three times).

**What happens**: Attackers forge commands or reuse legitimate commands to cause damage.

**Why hl_helper helps**: Every command has a unique nonce and a monotonic sequence number. A replayed command is immediately rejected. Even if an attacker captures the bytes, they can't forge new ones because signing keys are separate from TLS keys and require Ed25519 cryptography.

## What hl_helper Actually Protects

hl_helper is not an all-in-one security system. It does three things well:

1. **Confidentiality**: Everything between your control plane and agents is encrypted (mTLS 1.3, AES-256-GCM).
2. **Integrity**: All commands and results are signed. Tampering is detected instantly.
3. **Authenticity**: Each agent and the control plane prove their identity. Spoofing fails.

It does not protect against:
- **Physical access**: If someone has hands on your server, they can extract the root encryption key.
- **Compromised admin credentials**: If your admin password is stolen, so is your whole fleet. That's why we include tools for MFA, key rotation, and audit logging.
- **Zero-day exploits**: If a new kernel bug is found tomorrow, hl_helper cannot stop it. But we log it and help you recover.

## The Zero-Trust Model

hl_helper is built on "zero trust" — the idea that *every* message is verified, *every* actor is authenticated, and *every* action is logged. No machine is implicitly trusted just because it's on your network.

This means:
- A host cannot enumerate other hosts or eavesdrop on their traffic.
- A plugin cannot access secrets unless the server explicitly brokers the access.
- An admin action is logged and can be audited (and reversed, if needed).

## Where to Go From Here

Now that you understand *why* security matters, the next page explains *how* TLS works — the foundation of hl_helper's confidentiality. Then we'll show you exactly how hl_helper wires it all together.

See [TLS Basics](./10-tls-basics.md) →
