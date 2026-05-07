#!/usr/bin/env bash
set -euo pipefail
: "${HL_ENROLL_TOKEN:?required}"
: "${HL_SERVER:?required}"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) GOARCH=amd64 ;;
  arm64) GOARCH=arm64 ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

INSTALL_PATH=/usr/local/bin/hl-agent
STATE_DIR=/var/lib/hl-agent

sudo mkdir -p "$STATE_DIR"
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

sudo HL_ENROLL_TOKEN="$HL_ENROLL_TOKEN" HL_SERVER="$HL_SERVER" "$INSTALL_PATH" enroll

sudo cp "$(dirname "$0")/launchd/com.hl.agent.plist" /Library/LaunchDaemons/com.hl.agent.plist
sudo launchctl load -w /Library/LaunchDaemons/com.hl.agent.plist
echo "hl-agent installed + enrolled (darwin)"
