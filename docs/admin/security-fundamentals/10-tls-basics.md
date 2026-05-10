---
title: TLS Basics
status: stable
---

# TLS Basics

TLS (Transport Layer Security) is the standard way the internet encrypts and authenticates connections. If you've ever visited an HTTPS website, you've used TLS. This page explains how it works in non-technical language, so you can understand what hl_helper is doing under the hood.

## What TLS Does (In Three Bullets)

1. **Confidentiality**: Everything sent between two machines is encrypted. Only the sender and receiver can read it.
2. **Integrity**: If an attacker modifies a message in transit, the receiver detects it immediately and rejects it.
3. **Authentication**: Both sides prove they are who they claim to be. You're not talking to a fake server; the server is not talking to a fake client.

## A Simplified TLS Handshake

Imagine two people who have never met want to exchange secret messages:

1. **Alice** says: "Hi, I'm Alice. Here's a list of scrambling methods I can use."
2. **Bob** says: "Hi, I'm Bob. I have a certificate (proof I'm really Bob). Let's use this scrambling method."
3. Alice checks Bob's certificate. If it's valid, she says: "Okay, I believe you're Bob."
4. They both generate a temporary shared secret using math that only they know.
5. From now on, all messages are scrambled with that secret.

In TLS, step 2 is where certificates come in. Bob proves he's Bob by showing a certificate — a digital document signed by someone both Alice and Bob trust.

## Certificates and Trust Chains

A certificate is a file that says "This public key belongs to Bob" and is signed by someone who is trusted to know who Bob is.

**Example chain**:
- **Root CA** (e.g., DigiCert) says: "We, DigiCert, are trustworthy."
- **Intermediate CA** (maybe your company's CA) says: "DigiCert trusts us."
- **Leaf certificate** (your actual server) says: "The Intermediate CA trusts that this key belongs to example.com."

Your browser comes with Root CAs pre-installed. When you visit example.com, the server sends its leaf certificate plus the chain back to a Root CA you trust. Your browser verifies the chain and decides whether to trust the connection.

**Why chains exist**: It's inefficient for every website to be directly signed by a Root CA. Chains let you scale trust: one Root signs a few Intermediates, and those sign thousands of servers.

## Public-Key Cryptography (Simplified)

TLS uses **public-key cryptography**: two linked keys (one public, one private).

- Your **private key** is secret. Only you have it. Never share it.
- Your **public key** is like a mailbox — anyone can drop a message in (encrypt with your public key), but only you can read it (decrypt with your private key).

In TLS:
- The server has a private key (secret).
- The server sends you its public key (in the certificate).
- You encrypt a shared secret with the server's public key.
- Only the server (with the private key) can decrypt it.

This happens before you exchange any actual data, so the shared secret is never sent in plaintext.

## mTLS: Both Sides Prove Who They Are

Regular TLS (the HTTPS on websites) authenticates only the server. Your browser verifies the server is real, but the server doesn't verify your browser is real. That's fine for public websites.

**mTLS (mutual TLS)** authenticates both sides:

1. Client sends its certificate to the server.
2. Server verifies the client certificate.
3. Server sends its certificate to the client.
4. Client verifies the server certificate.

Now both sides have proven their identity *before* any sensitive data is exchanged. This is what hl_helper uses for agent-to-server communication.

## Certificate Anatomy

A certificate has several important fields:

| Field | Example | Why It Matters |
|---|---|---|
| **Subject** | `CN=spiffe://fleet/host/abc123` | Who this cert belongs to |
| **Subject Alternative Name (SAN)** | `spiffe://fleet/host/abc123` (URI format) | Alternative names the cert is valid for |
| **Issuer** | `CN=hl_helper CA` | Who signed this cert |
| **Not Before** | 2025-01-01 | Cert becomes valid |
| **Not After** | 2025-01-08 | Cert expires |
| **Serial Number** | `a1b2c3d4...` | Unique identifier for this cert |
| **Public Key** | ECDSA P-256 key material | Used to encrypt messages to the owner |

The most important fields for our purposes are:
- **CN (Common Name)** — old-style name, mostly for humans to read
- **SAN** — modern way to name who the cert belongs to, can include many names
- **Not After** — when the cert expires and must be renewed
- **Issuer** — who signed this cert (must be in the trust chain)

## The Certificate Lifecycle

Certificates are temporary — they expire and must be renewed.

1. **Issuance**: Someone (usually an automated system) creates a certificate and signs it with a CA private key.
2. **Installation**: The certificate and its private key are installed on the server.
3. **Monitoring**: Before expiry, the server requests a new certificate.
4. **Renewal**: A new certificate is signed and installed.
5. **Revocation** (if compromised): The CA publishes the certificate serial in a revocation list. Clients check the list and reject the revoked cert.

Short-lived certificates (24 hours to 7 days) reduce the impact if a certificate is compromised — the attacker's window is small.

## Common TLS Pitfalls

### Pitfall 1: Self-Signed Certificate Without Trust Anchor

A certificate is signed by itself, not by a trusted CA. Your computer doesn't know if it's legitimate or an attack.

**Problem**: You can't tell if you're talking to your real server or an attacker's fake server.

**Solution**: Self-signed certs are okay for internal use *if* you verify the fingerprint out-of-band. hl_helper allows this but expects you to verify the cert before installing it.

### Pitfall 2: Expired Certificate

The `Not After` date has passed.

**Problem**: The certificate no longer proves anything. The recipient rejects the connection.

**Solution**: hl_helper automatically rotates certificates before expiry. Monitor the logs for "cert expires in X days" warnings.

### Pitfall 3: Hostname Mismatch

The certificate says it's for `example.com`, but you're connecting to `192.168.1.5`.

**Problem**: TLS rejects the connection because the certificate doesn't match the hostname you're connecting to.

**Solution**: hl_helper uses SPIFFE URIs instead of hostnames. SPIFFE URIs are in the SAN field and don't require DNS resolution.

### Pitfall 4: Mixed Protocols

You configure TLS 1.2, but the other side only supports TLS 1.0. They negotiate TLS 1.0, which is weak.

**Problem**: Old protocols have known weaknesses.

**Solution**: hl_helper enforces TLS 1.3 (the latest stable version) and only allows strong ciphers (AES-256-GCM and ChaCha20-Poly1305). Weak protocols are not negotiated.

### Pitfall 5: Weak Cipher Suite

The TLS handshake allows the use of DES or RC4 encryption.

**Problem**: Those ciphers can be broken.

**Solution**: hl_helper pins two modern ciphers and rejects all others.

## Certificates in hl_helper

hl_helper uses mTLS for all communication between the control plane and agents:

- **Server certificate**: Proves the control plane is legitimate.
- **Agent certificate**: Proves each host is legitimate.
- **Signing key** (Ed25519, separate): Used to sign all commands and results (this is *not* the TLS certificate, but it works together with it).

The next page, [mTLS in hl_helper](./11-mtls-in-hlhelper.md), shows exactly how this is wired up.
