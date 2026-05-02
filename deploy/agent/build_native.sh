#!/usr/bin/env bash
# Build agent binaries for the current platform without Docker (developer build).
set -euo pipefail

VERSION="${VERSION:-dev}"
COMMIT="${COMMIT:-$(git rev-parse --short HEAD 2>/dev/null || echo none)}"
DATE="${DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

cd "$(dirname "$0")/../../agent"
mkdir -p ../bin

for arch in amd64 arm64; do
    GOOS=linux GOARCH=$arch CGO_ENABLED=0 \
    go build -trimpath \
        -ldflags="-s -w -X main.version=$VERSION -X main.commit=$COMMIT -X main.date=$DATE" \
        -o "../bin/hl-agent-linux-$arch" ./cmd/hl-agent
done

echo "built:"
ls -la ../bin/
