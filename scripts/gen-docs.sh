#!/usr/bin/env bash
# gen-docs.sh — generate API reference markdown for all language surfaces.
#
# Each generator runs independently; failure of one does not abort the others.

set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OUT="$ROOT/docs/developer/api"
ERRORS=0

run() {
  local name="$1"; shift
  echo "==> $name"
  if ! "$@"; then
    echo "WARN: $name failed (continuing)" >&2
    ERRORS=$((ERRORS + 1))
  fi
}

gen_python() {
  command -v sphinx-build >/dev/null || { echo "sphinx-build not found"; return 1; }
  local src="$ROOT/scripts/sphinx-conf"
  local tmp; tmp="$(mktemp -d)"
  # Source dir = sphinx-conf (holds conf.py + index.rst).
  # conf.py inserts $ROOT/server onto sys.path so autodoc can import packages.
  sphinx-build -b markdown -c "$src" "$src" "$tmp" >/dev/null 2>&1 || return 1
  rm -rf "$OUT/python"; mkdir -p "$OUT/python"
  if compgen -G "$tmp/*.md" > /dev/null; then
    mv "$tmp"/*.md "$OUT/python/"
  fi
  cp "$src/python-index.md" "$OUT/python/index.md"
}

gen_agent() {
  command -v gomarkdoc >/dev/null || { echo "gomarkdoc not found"; return 1; }
  rm -rf "$OUT/agent"; mkdir -p "$OUT/agent"
  # Generate one combined file per package tree. gomarkdoc handles fan-out via
  # output pattern when given multiple packages; here we emit a single file.
  ( cd agent && gomarkdoc --output "$OUT/agent/agent.md" ./... ) || return 1
  cp "$ROOT/scripts/agent-index.md" "$OUT/agent/index.md"
}

gen_grpc() {
  command -v protoc >/dev/null || return 1
  command -v protoc-gen-doc >/dev/null || return 1
  rm -rf "$OUT/grpc"; mkdir -p "$OUT/grpc"
  # shellcheck disable=SC2046
  local protos
  protos=$(find "$ROOT/proto" -name "*.proto" -print)
  [ -z "$protos" ] && { echo "no .proto files found"; return 1; }
  # shellcheck disable=SC2086
  protoc --proto_path="$ROOT/proto" --doc_out="$OUT/grpc" --doc_opt=markdown,index.md $protos || return 1
}

gen_rest() {
  command -v npx >/dev/null || return 1
  # openapi.json is committed to docs/developer/api/rest/openapi.json.
  # Do NOT rm the rest/ dir — that would delete the source. Instead we
  # render in-place and let .gitignore drop the generated html.
  local oapi="$OUT/rest/openapi.json"
  if [ ! -f "$oapi" ]; then
    echo "openapi.json missing at $oapi"
    return 1
  fi
  npx --yes @redocly/cli build-docs "$oapi" -o "$OUT/rest/openapi.html" >/dev/null 2>&1 || return 1
  cp "$ROOT/scripts/rest-index.md" "$OUT/rest/index.md"
}

run "python"  gen_python
run "agent"   gen_agent
run "grpc"    gen_grpc
run "rest"    gen_rest

echo "==> done. errors: $ERRORS"
exit 0
