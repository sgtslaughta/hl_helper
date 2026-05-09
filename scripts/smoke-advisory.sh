#!/usr/bin/env bash
#
# Smoke-test the advisory pipeline end-to-end against a running dev stack.
#
# Assumes:
#   * `scripts/dev.sh up` already ran (server on :8000, advisory.db present)
#   * Admin token printed by dev.sh up is exported as $FLEET_ADMIN_TOKEN
#       OR passed via --token <hex>
#   * Optional: a host has already been enrolled. If none enrolled, the
#     match-host step is skipped with a warning.
#
# Flags:
#   --token <hex>   admin bearer token; defaults to $FLEET_ADMIN_TOKEN
#   --base <url>    server base URL; defaults to http://localhost:8000
#   --skip-osv      skip the long OSV sync (status + match-only)
#   --no-color      disable ANSI colours
#
# Exit code: 0 on success, non-zero on first failed check.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="$REPO/.dev/data/advisory.db"
FLEET_DB_PATH="$REPO/.dev/data/fleet.db"
BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${FLEET_ADMIN_TOKEN:-}"
SKIP_OSV=0
COLOR=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --token)     TOKEN="$2"; shift 2 ;;
        --base)      BASE_URL="$2"; shift 2 ;;
        --skip-osv)  SKIP_OSV=1; shift ;;
        --no-color)  COLOR=0; shift ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$TOKEN" ]]; then
    echo "ERROR: no admin token. Set \$FLEET_ADMIN_TOKEN or pass --token." >&2
    echo "       (the token is printed by ./scripts/dev.sh up)" >&2
    exit 2
fi

# ---- formatting ----
if [[ $COLOR -eq 1 && -t 1 ]]; then
    C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_FAIL=$'\033[31m'; C_DIM=$'\033[36m'; C_END=$'\033[0m'
else
    C_OK=""; C_WARN=""; C_FAIL=""; C_DIM=""; C_END=""
fi
step()   { printf "%s[smoke]%s %s\n" "$C_DIM" "$C_END" "$*"; }
ok()     { printf "  %s✓%s %s\n" "$C_OK" "$C_END" "$*"; }
warn()   { printf "  %s!%s %s\n" "$C_WARN" "$C_END" "$*"; }
fail()   { printf "  %s✗%s %s\n" "$C_FAIL" "$C_END" "$*" >&2; exit 1; }

PY="$REPO/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

q_db() {
    # SQL → single value. Args: <db_path> <sql>
    "$PY" -c "
import sqlite3, sys
try:
    c = sqlite3.connect('file:'+sys.argv[1]+'?mode=ro', uri=True, timeout=2)
    print(c.execute(sys.argv[2]).fetchone()[0])
except Exception as e:
    print('ERR:'+str(e))
" "$1" "$2"
}

curl_q() {
    # Args: <method> <path> [<extra args...>]
    local method="$1"; shift
    local path="$1"; shift
    curl -s -X "$method" -H "Authorization: Bearer $TOKEN" "$BASE_URL$path" "$@"
}

# ---- 0. Sanity ----
step "checking server reachability $BASE_URL"
HEALTH="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/openapi.json" || true)"
[[ "$HEALTH" =~ ^(200|204)$ ]] || fail "server not reachable ($HEALTH)"
ok "server up"

step "checking auth (admin bearer via /v1/advisories/feeds/status)"
AUTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$BASE_URL/v1/advisories/feeds/status")"
[[ "$AUTH_CODE" == "200" ]] || fail "admin token rejected ($AUTH_CODE)"
ok "admin bearer accepted"

# ---- 1. Initial feed status ----
step "GET /v1/advisories/feeds/status"
STATUS_JSON="$(curl_q GET /v1/advisories/feeds/status)"
echo "$STATUS_JSON" | grep -q '"feed":"osv"' || fail "status response missing osv: $STATUS_JSON"
echo "$STATUS_JSON" | grep -q '"feed":"epss"' || fail "status response missing epss"
echo "$STATUS_JSON" | grep -q '"feed":"kev"' || fail "status response missing kev"
ok "all three feeds reported"

# ---- 2. Hosts + packages ----
HID="$(curl_q GET /v1/hosts | "$PY" -c "import json,sys; v=json.load(sys.stdin); print(v[0]['id'] if v else '')")"
if [[ -n "$HID" ]]; then
    step "host enrolled: $HID"
    PKG_COUNT="$(q_db "$FLEET_DB_PATH" "SELECT COUNT(*) FROM host_packages WHERE host_id='$HID'")"
    [[ "$PKG_COUNT" =~ ^[0-9]+$ && "$PKG_COUNT" -gt 0 ]] && ok "host_packages: $PKG_COUNT" || warn "host_packages=0 (waiting for inventory?)"
else
    warn "no host enrolled — skipping match-host check"
fi

# ---- 3. Optional OSV sync ----
if [[ $SKIP_OSV -eq 0 ]]; then
    OSV_BEFORE="$(q_db "$DB_PATH" "SELECT COUNT(*) FROM advisories")"
    LOG="$REPO/.dev/server.log"
    # Mark current log size so we only count NEW osv_done lines after our trigger.
    LOG_BEFORE_BYTES="$(stat -c '%s' "$LOG" 2>/dev/null || echo 0)"

    step "triggering OSV sync (advisories before: $OSV_BEFORE)"
    SYNC_RESP="$(curl_q POST '/v1/advisories/feeds/sync?feed=osv')"
    echo "$SYNC_RESP" | grep -q '"accepted"' || fail "sync accept failed: $SYNC_RESP"
    ok "sync accepted"

    step "waiting for osv_done in server log (timeout 15min)"
    DEADLINE=$(( $(date +%s) + 900 ))
    while [[ $(date +%s) -lt $DEADLINE ]]; do
        # only consider log lines written AFTER we triggered
        if tail -c +$((LOG_BEFORE_BYTES + 1)) "$LOG" 2>/dev/null | grep -q "advisory_worker.osv_done"; then break; fi
        if tail -c +$((LOG_BEFORE_BYTES + 1)) "$LOG" 2>/dev/null | grep -q "advisory_worker.feed_error"; then
            fail "feed_error in server log; check $LOG"
        fi
        sleep 10
        # responsiveness check during sync
        T=$( { time curl -s -o /dev/null -H "Authorization: Bearer $TOKEN" "$BASE_URL/v1/advisories/feeds/status"; } 2>&1 | awk '/^real/{print $2}')
        printf "    %sin-flight%s %s — feeds/status: %s\n" "$C_DIM" "$C_END" "$(date +%H:%M:%S)" "$T"
    done
    tail -c +$((LOG_BEFORE_BYTES + 1)) "$LOG" 2>/dev/null | grep -q "advisory_worker.osv_done" || fail "osv_done never observed within 15min"
    OSV_AFTER="$(q_db "$DB_PATH" "SELECT COUNT(*) FROM advisories")"
    AFF_AFTER="$(q_db "$DB_PATH" "SELECT COUNT(*) FROM affected_packages")"
    SIZE="$(stat -c '%s' "$DB_PATH")"
    ok "OSV done: advisories=$OSV_AFTER affected=$AFF_AFTER size=$((SIZE/1024/1024))MB"

    step "checking ecosystem allowlist applied"
    ECOS="$(q_db "$DB_PATH" "SELECT COUNT(DISTINCT ecosystem) FROM affected_packages")"
    [[ "$ECOS" -le 20 ]] && ok "ecosystem count: $ECOS (filtered)" || warn "ecosystems=$ECOS (filter may not be active)"
fi

# ---- 4. Match host ----
if [[ -n "$HID" ]]; then
    step "triggering rescan for $HID"
    curl_q POST "/v1/hosts/$HID/rescan" > /dev/null
    ok "rescan queued"

    step "waiting for match_done (timeout 60s)"
    DEADLINE=$(( $(date +%s) + 60 ))
    while [[ $(date +%s) -lt $DEADLINE ]]; do
        HA="$(q_db "$FLEET_DB_PATH" "SELECT COUNT(*) FROM host_advisories WHERE host_id='$HID'")"
        if [[ "$HA" =~ ^[0-9]+$ && "$HA" -gt 0 ]]; then break; fi
        sleep 3
    done
    HA="$(q_db "$FLEET_DB_PATH" "SELECT COUNT(*) FROM host_advisories WHERE host_id='$HID'")"
    if [[ "$HA" =~ ^[0-9]+$ && "$HA" -gt 0 ]]; then
        ok "host_advisories: $HA"
    else
        if [[ $SKIP_OSV -eq 1 ]]; then
            warn "host_advisories=0 — expected, OSV sync was skipped"
        else
            fail "host_advisories=0 after match — check matcher.py / advisory.db"
        fi
    fi
fi

# ---- 5. Final API endpoint snapshot ----
step "final feed status"
curl_q GET /v1/advisories/feeds/status | "$PY" -m json.tool 2>/dev/null || true

step "done"
ok "smoke-test passed"
