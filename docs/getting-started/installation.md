# Installation

Instructions for deploying the HL Helper control plane.

!!! note "Under construction"
    Detailed installation instructions are being written. Check back soon.

## Prerequisites

- Python 3.12+
- PostgreSQL 15+ (or SQLite for development)

## Quick Install

```bash
pip install hl_helper
```

## Container Deployment

```bash
docker run -d -p 8000:8000 ghcr.io/hlhelper/hl_helper:latest
```
