#!/usr/bin/env bash
# Local dev: server (uvicorn --reload) + webui (next dev) + log tail.
#
# Why: rebuilding the compose images on every UI tweak is slow and produces
# minified chunks where errors are unreadable. Running the stack natively gives
# hot reload, full source maps, and Python autoreload.
#
# Usage:
#   scripts/dev.sh up      # start (default if no arg)
#   scripts/dev.sh down    # stop both
#   scripts/dev.sh logs    # tail both logs
#   scripts/dev.sh status  # PID + port check
#   scripts/dev.sh reset   # nuke .dev/, server data, webui caches
#   scripts/dev.sh server  # only server
#   scripts/dev.sh webui   # only webui
#
# State lives in .dev/ (PID files, logs, sqlite DB, signing CA).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

DEV_DIR="$REPO/.dev"
DATA_DIR="$DEV_DIR/data"
LOG_SERVER="$DEV_DIR/server.log"
LOG_WEBUI="$DEV_DIR/webui.log"
PID_SERVER="$DEV_DIR/server.pid"
PID_WEBUI="$DEV_DIR/webui.pid"

ADMIN_TOKEN_FILE="$DEV_DIR/admin_token"
HOST_BIND="${HOST_BIND:-0.0.0.0}"
SERVER_PORT="${SERVER_PORT:-8000}"
WEBUI_PORT="${WEBUI_PORT:-3000}"

mkdir -p "$DEV_DIR" "$DATA_DIR"

# ──────────────────── helpers ────────────────────

log() { printf '\033[36m[dev]\033[0m %s\n' "$*"; }
err() { printf '\033[31m[dev]\033[0m %s\n' "$*" >&2; }

ensure_admin_token() {
	if [[ ! -s "$ADMIN_TOKEN_FILE" ]]; then
		openssl rand -hex 32 >"$ADMIN_TOKEN_FILE"
		log "minted admin token → $ADMIN_TOKEN_FILE"
	fi
}

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || { err "missing $1 in PATH"; exit 1; }
}

is_running() {
	local pidfile="$1"
	[[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

stop_pid() {
	local pidfile="$1" name="$2"
	if is_running "$pidfile"; then
		local pid; pid=$(cat "$pidfile")
		log "stopping $name (pid=$pid)"
		kill "$pid" 2>/dev/null || true
		# wait up to 10s for graceful exit
		for _ in $(seq 1 20); do
			kill -0 "$pid" 2>/dev/null || break
			sleep 0.5
		done
		kill -9 "$pid" 2>/dev/null || true
	fi
	rm -f "$pidfile"
}

# ──────────────────── server ────────────────────

start_server() {
	require_cmd uv
	ensure_admin_token

	if is_running "$PID_SERVER"; then
		log "server already running (pid=$(cat "$PID_SERVER"))"
		return
	fi

	local admin_token; admin_token=$(cat "$ADMIN_TOKEN_FILE")
	log "starting server on :$SERVER_PORT (data=$DATA_DIR, autoreload)"

	# Pydantic settings reads FLEET_*; cookie_secure=false so HTTP dev sets cookies.
	(
		cd "$REPO"
		FLEET_DATA_DIR="$DATA_DIR" \
		FLEET_DB_URL="sqlite+aiosqlite:///$DATA_DIR/fleet.db" \
		FLEET_ADMIN_TOKEN="$admin_token" \
		FLEET_COOKIE_SECURE=false \
		exec uv run uvicorn server.app.main:app \
			--host "$HOST_BIND" \
			--port "$SERVER_PORT" \
			--reload \
			--reload-dir server \
			>>"$LOG_SERVER" 2>&1
	) &
	echo $! >"$PID_SERVER"
	disown

	# wait for /openapi.json
	for _ in $(seq 1 60); do
		if curl -sf "http://127.0.0.1:$SERVER_PORT/openapi.json" >/dev/null 2>&1; then
			log "server healthy"
			return
		fi
		sleep 0.5
	done
	err "server did not become healthy in 30s; check $LOG_SERVER"
	return 1
}

# ──────────────────── webui ────────────────────

ensure_webui_deps() {
	if [[ ! -d "$REPO/webui/node_modules" ]]; then
		log "installing webui deps (first run)…"
		(cd "$REPO/webui" && npm install --no-audit --no-fund)
	fi
}

start_webui() {
	require_cmd npm
	ensure_webui_deps

	if is_running "$PID_WEBUI"; then
		log "webui already running (pid=$(cat "$PID_WEBUI"))"
		return
	fi

	log "starting webui on :$WEBUI_PORT (next dev, hot reload, source maps)"

	(
		cd "$REPO/webui"
		# Proxy handler reads INTERNAL_API_BASE per request; hot edits to
		# routes/components reload automatically without container rebuild.
		INTERNAL_API_BASE="http://127.0.0.1:$SERVER_PORT" \
		PORT="$WEBUI_PORT" \
		HOSTNAME="$HOST_BIND" \
		NEXT_TELEMETRY_DISABLED=1 \
		FLEET_PWA=0 \
		exec npm run dev -- --hostname "$HOST_BIND" --port "$WEBUI_PORT" \
			>>"$LOG_WEBUI" 2>&1
	) &
	echo $! >"$PID_WEBUI"
	disown

	for _ in $(seq 1 60); do
		if curl -sf "http://127.0.0.1:$WEBUI_PORT/" >/dev/null 2>&1; then
			log "webui ready"
			return
		fi
		sleep 0.5
	done
	err "webui did not respond in 30s; check $LOG_WEBUI"
}

# ──────────────────── bootstrap helper ────────────────────

bootstrap_owner() {
	local email="${1:-owner@example.com}" password="${2:-Hunter2!ChangeMeSoon}"
	local admin_token; admin_token=$(cat "$ADMIN_TOKEN_FILE")

	# mint a one-time bootstrap token directly via Python
	local token
	token=$(uv run python -c "
import asyncio, secrets, hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from server.app.models.bootstrap_token import BootstrapToken

async def main():
    eng = create_async_engine('sqlite+aiosqlite:///$DATA_DIR/fleet.db')
    sm = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    raw = secrets.token_urlsafe(32)
    h = hashlib.sha256(raw.encode()).digest()
    async with sm() as s:
        t = BootstrapToken(token_hash=h, expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        s.add(t)
        await s.commit()
    print(raw)

asyncio.run(main())
")
	log "bootstrap token minted, redeeming…"
	curl -sS -X POST -H 'Content-Type: application/json' \
		-d "{\"token\":\"$token\",\"email\":\"$email\",\"password\":\"$password\"}" \
		"http://127.0.0.1:$SERVER_PORT/v1/bootstrap/owner" | head -c 300
	echo
	log "owner provisioned: $email / $password"
}

# ──────────────────── commands ────────────────────

cmd_up() {
	start_server
	start_webui

	# bootstrap if no users exist (best-effort)
	if [[ ! -f "$DEV_DIR/.bootstrapped" ]]; then
		bootstrap_owner || log "bootstrap skipped (already provisioned?)"
		touch "$DEV_DIR/.bootstrapped"
	fi

	cat <<EOF

  hl_helper dev stack up
  ──────────────────────
  WebUI:  http://localhost:$WEBUI_PORT
  Server: http://localhost:$SERVER_PORT
  Login:  owner@example.com / Hunter2!ChangeMeSoon
  Token:  $(cat "$ADMIN_TOKEN_FILE")

  Logs:   scripts/dev.sh logs
  Status: scripts/dev.sh status
  Stop:   scripts/dev.sh down

EOF
}

cmd_down() {
	stop_pid "$PID_WEBUI" webui
	stop_pid "$PID_SERVER" server
	log "stopped"
}

cmd_logs() {
	touch "$LOG_SERVER" "$LOG_WEBUI"
	tail -F "$LOG_SERVER" "$LOG_WEBUI"
}

cmd_status() {
	for entry in "server:$PID_SERVER:$SERVER_PORT" "webui:$PID_WEBUI:$WEBUI_PORT"; do
		IFS=: read -r name pidfile port <<<"$entry"
		if is_running "$pidfile"; then
			log "$name running pid=$(cat "$pidfile") port=$port"
		else
			log "$name stopped"
		fi
	done
}

cmd_reset() {
	cmd_down
	log "wiping $DEV_DIR"
	rm -rf "$DEV_DIR"
	rm -rf "$REPO/webui/.next"
	mkdir -p "$DEV_DIR" "$DATA_DIR"
	log "reset complete"
}

cmd_bootstrap() { bootstrap_owner "${1:-}" "${2:-}"; }

case "${1:-up}" in
	up)        cmd_up ;;
	down|stop) cmd_down ;;
	logs|tail) cmd_logs ;;
	status|ps) cmd_status ;;
	reset)     cmd_reset ;;
	server)    start_server ;;
	webui)     start_webui ;;
	bootstrap) shift; cmd_bootstrap "$@" ;;
	restart)   cmd_down; cmd_up ;;
	*)
		err "usage: $0 {up|down|logs|status|reset|server|webui|bootstrap|restart}"
		exit 1
		;;
esac
