---
title: REST API
status: stable
---

# REST API

The HL Helper server exposes a REST API for host management, enrollment,
and administration.

## OpenAPI Specification

The full OpenAPI 3.1 specification is available as a JSON file:
[openapi.json](openapi.json)

## Endpoints

See the [Enrollment API](enrollment.md) for detailed endpoint documentation
including request/response examples and error formats.

## Authentication

Admin endpoints require a bearer token (`FLEET_ADMIN_TOKEN`).
Bootstrap tokens (`hlb_*`) are consumed once during enrollment.

## Error Format

All errors follow [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
(Problem Details for HTTP APIs):

```json
{
  "type": "/errors/<slug>",
  "title": "...",
  "status": 410,
  "detail": "...",
  "instance": "/v1/enroll",
  "trace_id": "..."
}
```
