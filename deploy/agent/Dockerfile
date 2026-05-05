# Multi-stage build for hl-agent.
# Produces a static binary in scratch image.
ARG GO_VERSION=1.25-bookworm
FROM --platform=$BUILDPLATFORM golang:${GO_VERSION} AS builder
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG COMMIT=none
ARG DATE=unknown
WORKDIR /src
COPY agent/go.mod agent/go.sum ./
RUN go mod download
COPY agent/ ./
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath \
    -ldflags="-s -w -X main.version=$VERSION -X main.commit=$COMMIT -X main.date=$DATE" \
    -o /out/hl-agent ./cmd/hl-agent

FROM scratch AS runtime
COPY --from=builder /out/hl-agent /usr/local/bin/hl-agent
ENTRYPOINT ["/usr/local/bin/hl-agent"]
