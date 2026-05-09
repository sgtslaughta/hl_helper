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

# pids_on_port — print all PIDs listening on the given TCP port, one per line.
# Empty stdout means port is free. Prefers `ss` because some Linux setups have
# a sandboxed lsof that returns nothing for ports the user does own (e.g.
# fuse.portal env), which would silently leave orphans alive.
pids_on_port() {
	local port="$1" out=""
	if command -v ss >/dev/null 2>&1; then
		out=$(ss -tlnpH "sport = :$port" 2>/dev/null \
			| grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
	fi
	if [[ -z "$out" ]] && command -v lsof >/dev/null 2>&1; then
		out=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u)
	fi
	if [[ -z "$out" ]] && command -v fuser >/dev/null 2>&1; then
		out=$(fuser -n tcp "$port" 2>/dev/null \
			| tr -s '[:space:]' '\n' | grep -E '^[0-9]+$' | sort -u)
	fi
	if [[ -n "$out" ]]; then
		printf '%s\n' "$out"
	fi
	return 0
}

# free_port — graceful TERM, then KILL anything bound to the port. Used both
# before start (to clear orphans) and during down/reset so a stale uvicorn
# never holds the port across a restart and silently serves the old DB.
free_port() {
	local port="$1" name="${2:-port $1}"
	local pids; pids=$(pids_on_port "$port")
	[[ -z "$pids" ]] && return 0

	log "freeing $name (:$port) — killing pid(s): $(echo "$pids" | tr '\n' ' ')"
	# shellcheck disable=SC2086
	kill -TERM $pids 2>/dev/null || true
	for _ in $(seq 1 20); do
		pids=$(pids_on_port "$port")
		[[ -z "$pids" ]] && return 0
		sleep 0.25
	done
	pids=$(pids_on_port "$port")
	if [[ -n "$pids" ]]; then
		# shellcheck disable=SC2086
		kill -KILL $pids 2>/dev/null || true
		sleep 0.5
	fi
}

stop_pid() {
	local pidfile="$1" name="$2"
	if is_running "$pidfile"; then
		local pid; pid=$(cat "$pidfile")
		log "stopping $name (pid=$pid)"
		# Kill the whole process group — uvicorn's --reload spawns a child
		# that survives SIGTERM to the parent and would keep the port bound.
		local pgid; pgid=$(ps -o pgid= "$pid" 2>/dev/null | tr -d ' ' || true)
		if [[ -n "$pgid" ]]; then
			kill -TERM "-$pgid" 2>/dev/null || true
		else
			kill "$pid" 2>/dev/null || true
		fi
		for _ in $(seq 1 20); do
			kill -0 "$pid" 2>/dev/null || break
			sleep 0.5
		done
		if [[ -n "$pgid" ]]; then
			kill -KILL "-$pgid" 2>/dev/null || true
		else
			kill -9 "$pid" 2>/dev/null || true
		fi
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

	# Tracked pid is dead but port may still be held by an orphan from a prior
	# run (uvicorn --reload spawns a child that outlives an unclean exit). If
	# we don't free it here, the next start binds to a different port or — worse
	# — the health probe hits the orphan and reports a stale DB as "healthy".
	rm -f "$PID_SERVER"
	free_port "$SERVER_PORT" "server"

	local admin_token; admin_token=$(cat "$ADMIN_TOKEN_FILE")

	# Resolve a routable host for advertised origins so install commands point
	# at something agents on the LAN can actually reach. Default `localhost` is
	# fine for same-box curls; prefer the first non-loopback IPv4 if available.
	# Override with FLEET_PUBLIC_HOST=<ip-or-name> to pin a specific value.
	local public_host="${FLEET_PUBLIC_HOST:-}"
	if [[ -z "$public_host" ]]; then
		public_host=$(ip -4 -o addr show scope global 2>/dev/null \
			| awk '{print $4}' | cut -d/ -f1 | head -n1)
		[[ -z "$public_host" ]] && public_host="localhost"
	fi
	# Dev runs uvicorn HTTP on $SERVER_PORT (no TLS). Match the scheme/port the
	# server actually listens on so mint URLs are reachable. For HTTPS, run
	# behind a reverse proxy and override FLEET_PUBLIC_URL.
	local public_url="${FLEET_PUBLIC_URL:-http://$public_host:$SERVER_PORT}"

	log "starting server on :$SERVER_PORT (data=$DATA_DIR, autoreload, public=$public_url)"

	# Pydantic settings reads FLEET_*; cookie_secure=false so HTTP dev sets cookies.
	# `setsid` puts the server in its own process group so we can SIGTERM the
	# whole tree (uv → uvicorn → reloader → app worker) without the signal
	# bouncing back to dev.sh itself.
	setsid bash -c "
		cd \"$REPO\"
		exec env \
			FLEET_DATA_DIR=\"$DATA_DIR\" \
			FLEET_DB_URL=\"sqlite+aiosqlite:///$DATA_DIR/fleet.db\" \
			FLEET_ADMIN_TOKEN=\"$admin_token\" \
			FLEET_PUBLIC_URL=\"$public_url\" \
			FLEET_COOKIE_SECURE=false \
			HL_CI_TOKEN=\"${HL_CI_TOKEN:-dev-ci-token}\" \
			HL_AGENT_DIST_DIR=\"${HL_AGENT_DIST_DIR:-$DATA_DIR/agent-dist}\" \
			uv run uvicorn server.app.main:app \
				--host \"$HOST_BIND\" \
				--port \"$SERVER_PORT\" \
				--reload \
				--reload-dir server \
			>>\"$LOG_SERVER\" 2>&1
	" </dev/null >/dev/null 2>&1 &
	echo $! >"$PID_SERVER"
	disown

	# wait for /openapi.json AND verify the listener is our process tree, not
	# a stranger that happened to be on this port. Without the pid check we
	# would silently report "healthy" against an unrelated server.
	local our_pid; our_pid=$(cat "$PID_SERVER")
	for _ in $(seq 1 60); do
		# Did our spawned process die? Stop probing.
		if ! kill -0 "$our_pid" 2>/dev/null; then
			err "server process exited before becoming healthy; check $LOG_SERVER"
			rm -f "$PID_SERVER"
			return 1
		fi
		if curl -sf "http://127.0.0.1:$SERVER_PORT/openapi.json" >/dev/null 2>&1; then
			local listening; listening=$(pids_on_port "$SERVER_PORT")
			# Listener PID may be a child of our_pid (uv → uvicorn → reloader).
			# Walk up parents to confirm relationship.
			if _pid_in_tree "$our_pid" $listening; then
				log "server healthy"
				return
			fi
			err "port :$SERVER_PORT held by foreign pid(s) $listening — aborting"
			rm -f "$PID_SERVER"
			return 1
		fi
		sleep 0.5
	done
	err "server did not become healthy in 30s; check $LOG_SERVER"
	return 1
}

# _pid_in_tree — return 0 if any of $2..$N has $1 as an ancestor (or equals $1).
_pid_in_tree() {
	local root="$1"; shift
	local pid
	for pid in "$@"; do
		local cur="$pid"
		for _ in $(seq 1 20); do
			[[ -z "$cur" || "$cur" == "0" ]] && break
			[[ "$cur" == "$root" ]] && return 0
			cur=$(ps -o ppid= "$cur" 2>/dev/null | tr -d ' ')
		done
	done
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

	rm -f "$PID_WEBUI"
	free_port "$WEBUI_PORT" "webui"

	log "starting webui on :$WEBUI_PORT (next dev, hot reload, source maps)"

	# setsid: own process group, so cmd_down's group-kill never reaches dev.sh.
	setsid bash -c "
		cd \"$REPO/webui\"
		exec env \
			INTERNAL_API_BASE=\"http://127.0.0.1:$SERVER_PORT\" \
			PORT=\"$WEBUI_PORT\" \
			HOSTNAME=\"$HOST_BIND\" \
			NEXT_TELEMETRY_DISABLED=1 \
			FLEET_PWA=0 \
			npm run dev -- --hostname \"$HOST_BIND\" --port \"$WEBUI_PORT\" \
			>>\"$LOG_WEBUI\" 2>&1
	" </dev/null >/dev/null 2>&1 &
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
") || { err "bootstrap token mint failed"; return 1; }
	log "bootstrap token minted, redeeming…"
	local body status
	body=$(curl -sS -o /tmp/.dev_bootstrap_body.$$ -w '%{http_code}' \
		-X POST -H 'Content-Type: application/json' \
		-d "{\"token\":\"$token\",\"email\":\"$email\",\"password\":\"$password\"}" \
		"http://127.0.0.1:$SERVER_PORT/v1/bootstrap/owner") || true
	status="$body"
	body=$(cat /tmp/.dev_bootstrap_body.$$ 2>/dev/null | head -c 300)
	rm -f /tmp/.dev_bootstrap_body.$$
	if [[ "$status" != "200" && "$status" != "201" && "$status" != "204" ]]; then
		err "bootstrap redeem failed (HTTP $status): $body"
		return 1
	fi
	log "owner provisioned: $email / $password"
}

# ──────────────────── commands ────────────────────

cmd_up() {
	start_server
	start_webui

	# bootstrap if no users exist. Marker only set on real success so a failed
	# attempt (e.g. server not yet ready, or talking to an orphan with empty DB)
	# does not poison subsequent runs.
	if [[ ! -f "$DEV_DIR/.bootstrapped" ]]; then
		if bootstrap_owner; then
			touch "$DEV_DIR/.bootstrapped"
		else
			log "bootstrap failed; will retry on next 'up' or via 'scripts/dev.sh bootstrap'"
		fi
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
	# Belt-and-suspenders: kill anything still bound to our ports so a stale
	# uvicorn reloader child or next-dev worker can't ghost into the next run.
	free_port "$WEBUI_PORT" "webui"
	free_port "$SERVER_PORT" "server"
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
