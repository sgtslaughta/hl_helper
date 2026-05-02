#!/usr/bin/env bash
set -euo pipefail

VERSION="${VERSION:-dev}"
COMMIT="${COMMIT:-$(git rev-parse --short HEAD 2>/dev/null || echo none)}"
DATE="${DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64,linux/arm/v7}"
IMAGE="${IMAGE:-hl-agent}"
TAG="${TAG:-$VERSION}"

cd "$(dirname "$0")/../.."

docker buildx build \
    --platform "$PLATFORMS" \
    --build-arg "VERSION=$VERSION" \
    --build-arg "COMMIT=$COMMIT" \
    --build-arg "DATE=$DATE" \
    --tag "$IMAGE:$TAG" \
    --file deploy/agent/Dockerfile \
    "${@}" \
    .
