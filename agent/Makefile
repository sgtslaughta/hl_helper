.PHONY: build build-linux-amd64 build-linux-arm64 build-darwin-amd64 build-darwin-arm64 build-all test vet fmt lint race leakcheck

VERSION ?= dev
COMMIT  ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo none)
DATE    ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
LDFLAGS := -X main.version=$(VERSION) -X main.commit=$(COMMIT) -X main.date=$(DATE)

build:
	go build -ldflags '$(LDFLAGS)' -o bin/hl-agent ./cmd/hl-agent

build-linux-amd64:
	GOOS=linux GOARCH=amd64 go build -ldflags '$(LDFLAGS)' -o bin/hl-agent-linux-amd64 ./cmd/hl-agent

build-linux-arm64:
	GOOS=linux GOARCH=arm64 go build -ldflags '$(LDFLAGS)' -o bin/hl-agent-linux-arm64 ./cmd/hl-agent

build-darwin-amd64:
	GOOS=darwin GOARCH=amd64 go build -ldflags '$(LDFLAGS)' -o bin/hl-agent-darwin-amd64 ./cmd/hl-agent

build-darwin-arm64:
	GOOS=darwin GOARCH=arm64 go build -ldflags '$(LDFLAGS)' -o bin/hl-agent-darwin-arm64 ./cmd/hl-agent

build-all: build-linux-amd64 build-linux-arm64 build-darwin-amd64 build-darwin-arm64

test:
	go test ./...

vet:
	go vet ./...

fmt:
	gofmt -s -w .

lint:
	go vet ./...

race:
	go test -race -count=1 ./...

leakcheck:
	go test -count=1 ./...
