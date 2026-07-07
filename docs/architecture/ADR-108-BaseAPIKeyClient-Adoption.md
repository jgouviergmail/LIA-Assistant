# ADR-108: BaseAPIKeyClient Adoption — Hardened Base, Deterministic Client Lifecycle, and Migration of the API-Key Connector Clients

**Status**: ✅ IMPLEMENTED (2026-07-07)
**Author**: Claude Code (Opus 4.8)
**Related**: [ADR-107](ADR-107-Dead-Code-Remediation-S7.md) (identified `BaseAPIKeyClient` as unused-but-valuable), [ADR-017](ADR-017-Rate-Limiting-Architecture.md) (rate limiting), [ADR-015](ADR-015-ConnectorTool-Base-Class-Pattern.md) (connector tool pattern)

## Context

`BaseAPIKeyClient` existed (tested, scaffolded by `scripts/scaffold.py`) but no
production client inherited it. The three API-key connector clients (Brave,
OpenWeatherMap, Perplexity) each hand-rolled **in-process** rate limiting —
incorrect under multiple workers (real rate = N × limit against paid APIs) —
and had no circuit breaker. Deep pre-analysis also found:

- the base itself carried an audited layering defect (6 raw `HTTPException`
  raises from a client layer) and reached into the CircuitBreaker's private
  API (`cb._lock` / `_should_allow_request()` / `_reject_request()`), a
  pattern duplicated in `base_oauth_client` and `base_apple_client`;
- a real lifecycle leak: pooled `httpx.AsyncClient`s created per tool call /
  per run and **never closed** (zero `close()` call sites);
- **PhilipsHue is NOT a candidate** (first instinct reversed by analysis):
  dual local/remote mode, OAuth token refresh with credential re-encryption,
  `HueBridgeCredentials`, deliberate BaseAppleClient-style composition.
  Wikipedia is keyless; media/TTS/LLM clients belong to other abstractions.

## Decision

Adopt in five steps, characterization-first (the public contract of each
client is pinned by tests written against the OLD implementation and kept
verbatim through the migration):

- **F0 — harden the base first**: domain error contract
  (`ExternalServiceError` for circuit-open and 401/403 — the
  `raise_google_api_error` model; `httpx.HTTPStatusError` for non-auth 4xx;
  `MaxRetriesExceededError` for retry exhaustion with `last_error` tracked;
  `RateLimitError` for client-side limiting), `rate_limit_per_second`
  widened to `float` (free tiers) with `max(1, int(×60))` for the Redis
  window, per-client timeout hook `_get_http_timeout()` and
  `follow_redirects` class attr, `user_id: UUID | None` (system callers).
  A public **`CircuitBreaker.check()`** was added to the resilience module
  (the body of `__aenter__`, now DRY-shared with `protect()`), and the
  private-API usage was eliminated from all three bases (api-key, oauth,
  apple — the apple one gains the lock, real state, retry_after and the
  rejected metric).
- **F1 — deterministic lifecycle**: `ToolDependencies.aclose()` closes every
  cached connector client at end of run (wired in the success and error
  cleanup paths of `stream_chat_response` and in the warmup helper — same
  rationale as the voice-service cleanup); direct instantiation sites
  (web_search ×2, heartbeat context_aggregator + geocoding) got try/finally
  closes (briefing already closed — the exemplary pattern). The
  KE/interests per-user client caches are bounded singletons and keep their
  pooling role.
- **F2/F3/F4 — migrate Brave, OpenWeatherMap, Perplexity** as
  `BaseAPIKeyClient` subclasses with **unchanged constructors and method
  signatures**: Brave keeps its None-on-error contract (`search()` wraps
  `_make_request`); OWM keeps its raising contract, list-returning geo
  endpoints (`geo/1.0/*` under the same host) and the timezone-aware daily
  aggregation; Perplexity keeps its POST payload shape and empty-choices
  fallbacks. 37 characterization tests (13+14+10) stayed green across the
  swap.

**Post-review hardenings** (from the staged-diff review): a non-numeric
`Retry-After` (RFC 7231 HTTP-date) falls back to exponential backoff instead
of crashing the 429 loop; a malformed body on a 200 is treated as a
transient service failure (circuit-breaker failure + retry, then
`MaxRetriesExceededError` keeping the decode error) — restoring the legacy
clients' retry-on-decode semantics.

**Documented intentional deltas** (visible behavior): 5xx are now retried
before failing; retry exhaustion surfaces as `MaxRetriesExceededError`
(briefing's weather fetch `except` was synced and classifies from
`last_error`); 401 surfaces as `ExternalServiceError` instead of
`ValueError` (all consumers catch broadly — verified); clients now share a
per-service circuit breaker and use the Redis rate limiter when
`RATE_LIMIT_ENABLED` (local time-based fallback otherwise, as before).

## Consequences

- Horizontal-scaling-correct rate limiting and cascade protection on paid
  APIs; one place to evolve retry/backoff policy; scaffold and production
  finally agree; pooled clients no longer leak sockets until GC.
- Test hygiene: characterization harness (`characterization_harness.py`,
  httpx.MockTransport-based, implementation-agnostic) reusable for future
  client work; the process-global circuit-breaker registry is isolated per
  test (a latent order-dependence trap fixed in both base and
  characterization suites).
- Out of scope, intentionally: PhilipsHue (composition is the right pattern
  there), Wikipedia (keyless), google_geocoding helpers (Google family),
  image/TTS clients (LLM-provider axis).

## Verification

Per step: green baseline → change → characterization green verbatim →
targeted consumer suites (connectors 332-354, briefing 60, heartbeat,
perplexity tools) → repo-wide gates (ruff/black; mypy green incl. all 38
client files) → full suite (~10.1k tests, zero new failures at every
checkpoint: F0 10,102 / F1 10,107 / F2 10,120) → fresh Docker boot to
healthy → in-container runtime smoke (the three migrated clients
instantiate, inherit the base, close idempotently; Brave's None-on-error
verified live).
