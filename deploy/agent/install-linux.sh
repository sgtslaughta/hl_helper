#!/usr/bin/env bash
set -euo pipefail

: "${HL_ENROLL_TOKEN:?required}"
: "${HL_SERVER:?required}"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) GOARCH=amd64 ;;
  aarch64|arm64) GOARCH=arm64 ;;
  armv7l) GOARCH=armv7 ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

INSTALL_PATH=/usr/local/bin/hl-agent
STATE_DIR=/var/lib/hl-agent

mkdir -p "$STATE_DIR"
curl -fsSL "$HL_SERVER/v1/agent-releases/latest?os=linux&arch=$GOARCH" -o /tmp/release.json || \
  curl -fsSL "$HL_SERVER/agent/$GOARCH/hl-agent" -o /tmp/hl-agent

if [ -f /tmp/release.json ]; then
  RELEASE_ID=$(jq -r .id /tmp/release.json)
  SHA=$(jq -r .sha256 /tmp/release.json)
  curl -fsSL "$HL_SERVER/v1/agent-releases/$RELEASE_ID/binary?token=bootstrap" -o /tmp/hl-agent
  echo "$SHA  /tmp/hl-agent" | sha256sum -c -
fi

install -m 0755 /tmp/hl-agent "$INSTALL_PATH"
rm -f /tmp/hl-agent /tmp/release.json

install -m 0644 "$(dirname "$0")/systemd/hl-agent.service" /etc/systemd/system/hl-agent.service

HL_ENROLL_TOKEN="$HL_ENROLL_TOKEN" HL_SERVER="$HL_SERVER" "$INSTALL_PATH" enroll

systemctl daemon-reload
systemctl enable --now hl-agent.service
echo "hl-agent installed + enrolled"
