#!/usr/bin/env bash
# Build all hl_helper Docker images. Bulletproof version with pre-flight
# checks, clear error messages, and parallel builds.
#
# Usage:
#   ./scripts/build-images.sh                       # build all (server, webui, agent)
#   ./scripts/build-images.sh server webui          # build subset
#   TAG=v0.0.1 ./scripts/build-images.sh            # custom tag (default: dev)
#   PUSH=1 REGISTRY=ghcr.io/you ./scripts/build-images.sh   # tag + push
#   NO_CACHE=1 ./scripts/build-images.sh            # ignore build cache
#   PARALLEL=1 ./scripts/build-images.sh            # build images concurrently
#   PLATFORM=linux/arm64 ./scripts/build-images.sh  # cross-build
#   VERBOSE=1 ./scripts/build-images.sh             # plain progress output

set -Eeuo pipefail
shopt -s inherit_errexit 2>/dev/null || true

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# ---- config ----------------------------------------------------------------
TAG="${TAG:-dev}"
REGISTRY="${REGISTRY:-}"
PUSH="${PUSH:-0}"
NO_CACHE="${NO_CACHE:-0}"
PARALLEL="${PARALLEL:-0}"
PLATFORM="${PLATFORM:-linux/amd64}"
VERBOSE="${VERBOSE:-0}"

prefix=""
[[ -n "${REGISTRY}" ]] && prefix="${REGISTRY}/"

# ---- output helpers --------------------------------------------------------
if [[ -t 1 ]]; then
  C_RED=$'\033[0;31m'; C_GRN=$'\033[0;32m'; C_YLW=$'\033[0;33m'
  C_BLU=$'\033[0;34m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YLW=""; C_BLU=""; C_DIM=""; C_RST=""
fi

log()  { printf "%s==>%s %s\n" "${C_BLU}" "${C_RST}" "$*"; }
ok()   { printf "%s ok%s %s\n"  "${C_GRN}" "${C_RST}" "$*"; }
warn() { printf "%swarn%s %s\n" "${C_YLW}" "${C_RST}" "$*" >&2; }
die()  { printf "%serr%s  %s\n" "${C_RED}" "${C_RST}" "$*" >&2; exit 1; }

trap 'die "build script aborted (line ${LINENO})"' ERR

# ---- pre-flight ------------------------------------------------------------
preflight() {
  command -v docker >/dev/null 2>&1 \
    || die "docker not found in PATH. Install: https://docs.docker.com/engine/install/"

  docker info >/dev/null 2>&1 \
    || die "docker daemon not reachable. Start it (e.g. 'systemctl start docker') or check DOCKER_HOST."

  docker buildx version >/dev/null 2>&1 \
    || die "docker buildx not available. Install the buildx plugin or use Docker >= 23."

  if [[ "${PUSH}" == "1" && -z "${REGISTRY}" ]]; then
    die "PUSH=1 requires REGISTRY=<host>  (e.g. REGISTRY=ghcr.io/sgtslaughta PUSH=1 ...)"
  fi

  for f in deploy/server/Dockerfile deploy/webui/Dockerfile deploy/agent/Dockerfile deploy/aio/Dockerfile; do
    [[ -f "$f" ]] || die "missing dockerfile: $f"
  done

  # .dockerignore sanity: ensure server build deps aren't excluded.
  if grep -qxE 'agent' .dockerignore 2>/dev/null; then
    die ".dockerignore excludes 'agent/' but pyproject.toml lists it as a setuptools package. Server build will fail.
   Fix: remove the bare 'agent' line from .dockerignore (keep 'deploy/agent' if desired)."
  fi

  if grep -qxE 'server' .dockerignore 2>/dev/null; then
    die ".dockerignore excludes 'server/' which the server build needs."
  fi

  if grep -qxE 'webui' .dockerignore 2>/dev/null; then
    die ".dockerignore excludes 'webui/' which the webui build needs."
  fi

  ok "pre-flight checks passed"
}

# ---- build -----------------------------------------------------------------
build_one() {
  local name="$1"
  local dockerfile="$2"
  local context="$3"
  local image="${prefix}hl_helper-${name}:${TAG}"

  local args=(
    buildx build
    --platform "${PLATFORM}"
    --file "${dockerfile}"
    --tag "${image}"
    --load
  )
  [[ "${NO_CACHE}" == "1" ]] && args+=(--no-cache)
  [[ "${VERBOSE}" == "1" ]] && args+=(--progress=plain)
  args+=("${context}")

  log "building ${image}  (platform=${PLATFORM})"
  if docker "${args[@]}"; then
    ok "built ${image}"
  else
    die "build failed for ${name}. Re-run with VERBOSE=1 for full output."
  fi

  if [[ "${PUSH}" == "1" ]]; then
    log "pushing ${image}"
    docker push "${image}" || die "push failed for ${image}"
    ok "pushed ${image}"
  fi
}

dockerfile_for() {
  case "$1" in
    server) echo deploy/server/Dockerfile ;;
    webui)  echo deploy/webui/Dockerfile ;;
    agent)  echo deploy/agent/Dockerfile ;;
    aio)    echo deploy/aio/Dockerfile ;;
    *)      die "unknown target '$1' (valid: server, webui, agent, aio)" ;;
  esac
}

# ---- main ------------------------------------------------------------------
preflight

if [[ $# -eq 0 ]]; then
  TARGETS=(server webui agent)
else
  TARGETS=("$@")
fi

# Validate targets up front.
for t in "${TARGETS[@]}"; do dockerfile_for "$t" >/dev/null; done

if [[ "${PARALLEL}" == "1" && "${#TARGETS[@]}" -gt 1 ]]; then
  log "building ${#TARGETS[@]} images in parallel"
  pids=()
  for t in "${TARGETS[@]}"; do
    build_one "$t" "$(dockerfile_for "$t")" . &
    pids+=("$!")
  done
  rc=0
  for pid in "${pids[@]}"; do
    wait "$pid" || rc=$?
  done
  [[ $rc -eq 0 ]] || die "one or more parallel builds failed"
else
  for t in "${TARGETS[@]}"; do
    build_one "$t" "$(dockerfile_for "$t")" .
  done
fi

echo
log "summary:"
for t in "${TARGETS[@]}"; do
  printf "    %s%s%s\n" "${C_DIM}" "${prefix}hl_helper-${t}:${TAG}" "${C_RST}"
done

cat <<EOF

Smoke test single image:
  docker run --rm -p 8000:8000 ${prefix}hl_helper-server:${TAG}
  curl -fsS http://localhost:8000/v1/observability/health

Full stack via compose (server + webui):
  TAG=${TAG} docker compose -f deploy/compose/tier0-quickstart.yml up
  open http://localhost:3000
EOF
