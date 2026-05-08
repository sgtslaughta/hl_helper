#!/usr/bin/env bash
set -euo pipefail

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) GOARCH=amd64 ;;
  arm64) GOARCH=arm64 ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

INSTALL_PATH=/usr/local/bin/hl-agent

curl -fsSL "$HL_SERVER/v1/agent-releases/latest?os=darwin&arch=$GOARCH" -o /tmp/release.json || \
  curl -fsSL "$HL_SERVER/agent/$GOARCH/hl-agent" -o /tmp/hl-agent

if [ -f /tmp/release.json ]; then
  RELEASE_ID=$(jq -r .id /tmp/release.json)
  SHA=$(jq -r .sha256 /tmp/release.json)
  curl -fsSL "$HL_SERVER/v1/agent-releases/$RELEASE_ID/binary?token=bootstrap" -o /tmp/hl-agent
  echo "$SHA  /tmp/hl-agent" | shasum -a 256 -c -
fi

sudo install -m 0755 /tmp/hl-agent "$INSTALL_PATH"
rm -f /tmp/hl-agent /tmp/release.json

if [ -n "${HL_SERVER:-}" ] && [ -n "${HL_ENROLL_TOKEN:-}" ]; then
  sudo "$INSTALL_PATH" install --unattended --server "$HL_SERVER" --token "$HL_ENROLL_TOKEN"
else
  sudo "$INSTALL_PATH" install
fi
