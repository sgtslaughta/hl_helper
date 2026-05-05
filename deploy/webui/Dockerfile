# Multi-stage build for hl_helper webui (Next.js 15 standalone).
# Node 22 LTS required: several deps (@scalar/*, etc.) declare engines.node >=22.
ARG NODE_VERSION=22-alpine

FROM node:${NODE_VERSION} AS deps
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false
COPY webui/package.json webui/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund

FROM node:${NODE_VERSION} AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY webui ./
RUN npm run build

FROM node:${NODE_VERSION} AS runtime
RUN addgroup -S -g 10002 hl && adduser -S -u 10002 -G hl hl \
 && apk add --no-cache tini
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=builder --chown=hl:hl /app/.next/standalone ./
COPY --from=builder --chown=hl:hl /app/.next/static ./.next/static
COPY --from=builder --chown=hl:hl /app/public ./public
USER hl
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget -qO- http://localhost:3000/ >/dev/null 2>&1 || exit 1
ENTRYPOINT ["/sbin/tini", "--", "node", "server.js"]
