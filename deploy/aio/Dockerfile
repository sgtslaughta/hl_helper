# All-in-one hl_helper image: FastAPI control plane + Next.js web UI
# + hl-agent CLI, supervised by s6-overlay (PID 1, own signal handling + reaping).
#
# Architecture:
#   - s6-overlay v3 (PID 1; manages two long-running services)
#       fastapi   -> uvicorn server.app.main:app   :8000 (loopback only)
#       nextjs    -> node server.js                :3000 (public)
#   - hl-agent CLI shipped at /usr/local/bin/hl-agent (no s6 service:
#     agent is edge-deployed; binary is bundled for `docker exec` use,
#     dev/test, or a self-managed node profile).
#   - Next.js proxies /api/* (incl. /api/v1/events SSE/WSS) to FastAPI loopback.
#
# Public port: 3000 (HTTP). FastAPI is NOT exposed.
# Agent gRPC mTLS port :8444 is published when agent is enabled (separate surface).

ARG PYTHON_VERSION=3.12-slim-bookworm
ARG NODE_VERSION=22-bookworm-slim
ARG GO_VERSION=1.25-bookworm
ARG S6_OVERLAY_VERSION=3.2.0.2

# ---------- Stage 1: Python builder --------------------------------------
FROM python:${PYTHON_VERSION} AS py-builder
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
COPY pyproject.toml ./
COPY server ./server
COPY agent ./agent
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install . httpx

# ---------- Stage 2: Node deps + Next.js build ---------------------------
FROM node:${NODE_VERSION} AS node-builder
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
COPY webui/package.json webui/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund
COPY webui ./
RUN npm run build

# ---------- Stage 3: Go agent builder ------------------------------------
FROM --platform=$BUILDPLATFORM golang:${GO_VERSION} AS agent-builder
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=none
ARG DATE=unknown
WORKDIR /src
ENV CGO_ENABLED=0 \
    GOFLAGS=-trimpath
COPY agent/go.mod agent/go.sum ./
RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    go mod download
COPY agent/ ./
RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} \
    go build \
      -ldflags="-s -w -X main.version=${VERSION} -X main.commit=${COMMIT} -X main.date=${DATE}" \
      -o /out/hl-agent ./cmd/hl-agent

# ---------- Stage 4: Runtime --------------------------------------------
# python:3.12-slim-bookworm provides python3.12 + libpython3.12 from upstream
# (Debian bookworm only ships python3.11). Add Node 22, tini, s6-overlay on top.
FROM python:${PYTHON_VERSION} AS runtime

ARG S6_OVERLAY_VERSION
ENV S6_OVERLAY_VERSION=${S6_OVERLAY_VERSION} \
    S6_KEEP_ENV=1 \
    S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_VERBOSITY=1 \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    INTERNAL_API_BASE=http://127.0.0.1:8000 \
    DATABASE_URL=sqlite:////data/hl_helper.db \
    PYTHONUNBUFFERED=1 \
    PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

# System deps + Python 3.12 + Node 22 + tini + s6-overlay
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils gnupg; \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    apt-get purge -y --auto-remove gnupg; \
    case "$(dpkg --print-architecture)" in \
        amd64)  S6_ARCH=x86_64 ;; \
        arm64)  S6_ARCH=aarch64 ;; \
        armhf)  S6_ARCH=armhf ;; \
        *) echo "unsupported arch"; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" \
        | tar -C / -Jxpf -; \
    curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" \
        | tar -C / -Jxpf -; \
    # python3.12 already at /usr/local/bin/python3 from base; ensure `python` alias.
    ln -sf /usr/local/bin/python3 /usr/local/bin/python

# Non-root runtime user.
RUN groupadd -r -g 10001 hl && useradd -r -u 10001 -g hl -m -d /home/hl hl \
 && mkdir -p /data /app/server /app/webui /etc/hl-agent \
 && chown -R hl:hl /data /app /home/hl /etc/hl-agent

# Python site-packages + entry-point scripts (uvicorn, alembic) from builder.
COPY --from=py-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=py-builder /usr/local/bin /usr/local/bin
COPY --chown=hl:hl server /app/server

# Next.js standalone bundle.
COPY --from=node-builder --chown=hl:hl /app/.next/standalone /app/webui
COPY --from=node-builder --chown=hl:hl /app/.next/static /app/webui/.next/static
COPY --from=node-builder --chown=hl:hl /app/public /app/webui/public

# hl-agent CLI (bundled but not auto-started; edge-deployed component).
COPY --from=agent-builder /out/hl-agent /usr/local/bin/hl-agent

# s6 service definitions.
COPY deploy/aio/s6/ /etc/s6-overlay/s6-rc.d/
RUN set -eux; \
    chmod +x /etc/s6-overlay/s6-rc.d/fastapi/run \
             /etc/s6-overlay/s6-rc.d/nextjs/run; \
    mkdir -p /etc/s6-overlay/s6-rc.d/user/contents.d; \
    touch /etc/s6-overlay/s6-rc.d/user/contents.d/fastapi \
          /etc/s6-overlay/s6-rc.d/user/contents.d/nextjs

VOLUME ["/data"]
EXPOSE 3000
WORKDIR /app

# Liveness only: webui root + FastAPI openapi (auth-free). The real health
# endpoint (/v1/observability/health) requires ADMIN_TOKEN, so it can't be
# used here without coupling the image to a runtime secret.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/ >/dev/null \
     && curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null \
     || exit 1

# s6-overlay /init must run as PID 1 (provides its own signal handling + reaping).
ENTRYPOINT ["/init"]
