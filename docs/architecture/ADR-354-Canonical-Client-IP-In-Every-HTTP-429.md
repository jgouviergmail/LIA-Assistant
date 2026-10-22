# ADR-354: Canonical Client IP in Every HTTP 429

**Status:** Accepted

**Date:** 2026-10-19

## Context

An HTTP refusal must remain attributable when ordinary access logging is quiet.
The global limiter already emitted `global_rate_limit_exceeded`, but its warning
did not carry the client IP. Request completion records used the configurable
access-log level and path exclusions, so they could be absent from retained logs.
An operator could count refusals by path without reliably grouping them by caller.

The new admission control in
[ADR-353](ADR-353-API-HTTP-Scan-Bans-In-Shared-Redis.md) adds another producer of
HTTP 429. Logging each limiter independently would leave future producers with
the same gap. The response boundary already observes every HTTP response and
owns the request context and timing.

The identity decision already exists in
[`resolve_client_ip`](../../apps/api/src/core/client_ip.py). It prefers a valid,
canonical `CF-Connecting-IP`, then uses its existing peer-address fallback or
unknown marker. The trusted-proxy envelope in
[ADR-093](ADR-093-Security-Hardening-Proxy-XSS.md), refined by
[ADR-213](ADR-213-L-Identite-De-L-Appelant-Vient-D-Un-En-Tete-Qu-Il-Ne-Peut-Pas-Ecrire.md),
is a prerequisite: the reference API is exposed through loopback and the tunnel;
the demonstrator's edge and network envelope preserve the tunnel-only ingress.
Trusting Cloudflare's header depends on that deployment boundary.

## Decision

In [`LoggingMiddleware`](../../apps/api/src/core/middleware.py), every
`http.response.start` carrying status 429 emits `request_completed` at WARNING,
regardless of `HTTP_LOG_LEVEL` or ordinary path exclusions. This covers global,
endpoint and scan-protection refusals through the same response observer.
Other statuses retain their configured access-log level and exclusions.

The record carries `client_ip`, `method`, `path`, `status_code` and `duration_ms`,
with the existing `request_id` and structured request context. Logging resolves
the client address once per request and reuses that value at response start.
`global_rate_limit_exceeded` also carries the IP from the same resolver.
Neither path introduces another identity algorithm or parses raw
`X-Forwarded-For` as an application identity.

The logged path is the ASGI path, without the query string. The change adds no
request body, cookies, authorization header or credential fields. Records use
the existing JSON and PII-filtering pipeline from
[ADR-027](ADR-027-Structured-Logging.md). The IP is a JSON payload field, never a
Prometheus label or an indexed Loki label: caller addresses have unbounded
cardinality. The
[log collection configuration](../../infrastructure/observability/promtail/promtail-config.yml)
keeps payload fields queryable without promoting them to stream labels.
[Production Compose](../../docker-compose.prod.yml) runs Alloy with this
maintained Promtail-format configuration.

The observer remains pure ASGI and forwards each message unchanged. Timing ends
at response start, preserving the existing time-to-headers meaning for streaming
responses. It does not buffer a body or wait for a stream to finish. CORS wraps
the admission guards so an allowed browser origin can read their refusal body
and exposed `Retry-After` header; request identity and security headers remain
available on those responses.

## Alternatives considered

- **Promote all access logs to INFO or enable DEBUG globally.** This increases
  routine log volume and changes the operator's verbosity policy. A targeted
  WARNING preserves attribution for refusals while leaving ordinary traffic
  configurable.
- **Use Uvicorn access logs alone.** Their availability depends on server
  verbosity. They do not enforce the application-level structured warning
  contract and request context at every refusal.
- **Read raw X-Forwarded-For.** A visitor can supply entries that the proxy chain
  preserves. Selecting one independently reintroduces a caller-controlled
  identity instead of reusing the established resolver.
- **Index or label every IP in Loki or Prometheus.** This converts an unbounded
  caller population into stream or metric cardinality. Read-time JSON queries
  provide the required grouping without that storage and memory cost.

## Consequences and verification

New retained records support private grouping by client IP and route, with a
request identifier for correlation. IP addresses remain potentially identifying
security data under the existing access and retention policy. Shared or public
incident summaries must remove identifying addresses rather than publish those
operational groupings verbatim. Historical records missing an IP do not become
attributable retrospectively; an address cannot be inferred from a country,
another request or an unrelated rate-limit event.

An attack produces more WARNING records. Retention and collection capacity
must accommodate that operational signal; sampling would change the contract
that every refusal is attributable.

[`test_http429_trace.py`](../../apps/api/tests/unit/core/test_http429_trace.py)
executes real ASGI request/response paths and captures structured output through
a real standard-library logger at INFO. It verifies global and endpoint 429s,
excluded paths, trusted-header priority over a forged forwarded header, one IP
resolution in the logging observer, absence of sensitive request content and
unchanged logging for other statuses.
[`test_logging_middleware.py`](../../apps/api/tests/unit/core/test_logging_middleware.py)
retains the existing verbosity and exclusion coverage. Identity behavior and
its single-reader boundary are checked by
[`test_client_ip_resolution.py`](../../apps/api/tests/unit/core/test_client_ip_resolution.py)
and
[`test_client_ip_single_resolver_guard.py`](../../apps/api/tests/unit/test_client_ip_single_resolver_guard.py).
[`test_http_scan_protection.py`](../../apps/api/tests/unit/core/test_http_scan_protection.py)
covers guard refusals and their CORS/security headers;
[`test_promtail_label_cardinality_guard.py`](../../apps/api/tests/unit/test_promtail_label_cardinality_guard.py)
holds the bounded-label collection policy.

A separate bounded Docker qualification sent 30 synthetic requests through real
Uvicorn and HTTPX to a minimal FastAPI application using the actual middleware
and a disposable Redis. It verified WARNING completion records with a canonical
IPv6 address, refusal headers, forwarded-header rotation, ordinary resource and
session errors, and admission exemptions. This qualifies the implementation;
activation and runtime provenance remain instance-specific verification.

Deployment follow-up, 2026-10-19: an isolated native ARM64 probe of the production
derivative also verified canonical IP warning traces for both scan refusal
reasons at the configured production thresholds. Its Redis and network were
disposable, with no production requests or credentials. The subsequent API-only
activation passed readiness and verification of the installed source hashes.
This does not retrospectively identify old refusals or certify every external
proxy hop; the trusted-envelope requirements above remain operational constraints.

See [HTTP scan protection and refusal traceability](../technical/SECURITY.md)
for the operational contract.
