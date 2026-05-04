# HL Helper

Self-hosted, security-focused fleet manager for Linux/Unix homelabs.

## Overview

One control plane for many Linux/Unix hosts. Pulls together fleet update
management, container ops, terminal access, power control, and observability
into a single self-hosted application.

Designed for the gap between toy auto-updaters (Watchtower) and enterprise
tools (Spacewalk, Foreman, Satellite). Beginner-friendly to run, hardened
enough that a compromised host cannot pivot to the control plane.

## Key Features

- **Signed commands** -- every command cryptographically signed by the server
- **Sandboxed plugins** -- bubblewrap isolation with egress control
- **Multi-distro updates** -- apt, dnf, zypper with advisory classification
- **Hash-chained audit** -- tamper-evident audit log
- **Modern UI** -- real-time fleet dashboard
- **Single-container default** -- easy deployment, hardened upgrade path

## Getting Started

New to HL Helper? Start with the [Installation](getting-started/installation.md)
guide, then follow the [Quick Start](getting-started/quickstart.md).
