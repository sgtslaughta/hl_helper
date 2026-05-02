.PHONY: build test vet fmt lint

VERSION ?= dev
COMMIT  ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo none)
DATE    ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
LDFLAGS := -X main.version=$(VERSION) -X main.commit=$(COMMIT) -X main.date=$(DATE)

build:
	go build -ldflags '$(LDFLAGS)' -o bin/hl-agent ./cmd/hl-agent

test:
	go test ./...

vet:
	go vet ./...

fmt:
	gofmt -s -w .

lint:
	go vet ./...
