#!/usr/bin/env bash
# gen-docs.sh — generate API reference markdown for all language surfaces.

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
  local tmp; tmp="$(mktemp -d)"
  sphinx-build -b markdown -c scripts/sphinx-conf "$ROOT/server" "$tmp" >/dev/null
  rm -rf "$OUT/python"; mkdir -p "$OUT/python"
  mv "$tmp"/*.md "$OUT/python/" 2>/dev/null || true
  cp scripts/sphinx-conf/python-index.md "$OUT/python/index.md"
}

gen_agent() {
  command -v gomarkdoc >/dev/null || { echo "gomarkdoc not found"; return 1; }
  rm -rf "$OUT/agent"; mkdir -p "$OUT/agent"
  ( cd agent && gomarkdoc --output "$OUT/agent/{{.Name}}.md" ./... )
  cp scripts/agent-index.md "$OUT/agent/index.md"
}

gen_grpc() {
  command -v protoc >/dev/null || return 1
  command -v protoc-gen-doc >/dev/null || return 1
  rm -rf "$OUT/grpc"; mkdir -p "$OUT/grpc"
  protoc --doc_out="$OUT/grpc" --doc_opt=markdown,index.md proto/*.proto
}

gen_rest() {
  command -v npx >/dev/null || return 1
  rm -rf "$OUT/rest"; mkdir -p "$OUT/rest"
  npx --yes @redocly/cli build-docs "$OUT/rest/openapi.json" -o "$OUT/rest/openapi.html"
  cp scripts/rest-index.md "$OUT/rest/index.md"
}

run "python"  gen_python
run "agent"   gen_agent
run "grpc"    gen_grpc
run "rest"    gen_rest

echo "==> done. errors: $ERRORS"
exit 0
