# ADR-114: Connector Client Domain Error Contract — OAuth/Google/Microsoft/Places/Routes Alignment on the BaseAPIException Taxonomy

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-002](ADR-002-Unified-Error-Handling.md) (BaseAPIException taxonomy), [ADR-023](ADR-023-Error-Handling-Strategy.md) (error strategy), [ADR-108](ADR-108-BaseAPIKeyClient-Adoption.md) (F0 — same contract applied to `BaseAPIKeyClient`)

## Context

The 2026-07 audit flagged a layering defect: the connector **client layer**
(a domain layer) raised raw transport `fastapi.HTTPException` — 28 sites
across `base_oauth_client` (×8), `google_places_client` (×6),
`google_routes_client` (×6), `base_microsoft_client` (×4),
`base_google_client` (×3) and `microsoft_tasks_client` (×1). Raw raises are
untyped, invisible to Prometheus, unlogged by the central mechanism, and
violate review rule #18 (centralized raisers only). ADR-108/F0 had already
fixed the same defect in `BaseAPIKeyClient` one release earlier; this ADR
extends that contract to the whole OAuth family and the Google-direct
clients.

Three structural facts constrain the design:

- `BaseAPIException` **is** an `HTTPException` subclass (ADR-002): the
  repo's typed taxonomy carries HTTP semantics by design.
- The frontend (`apps/web/src/lib/api-client.ts`) reads the native FastAPI
  `{"detail": ...}` payload; two backend paths do `isinstance(e,
  HTTPException)` (`users/service.py` geocoding re-raise,
  `agents/tools/runtime_helpers.py` classification).
- Tool-layer classification (`handle_tool_exception`) keys on nothing but
  `type(e).__name__` and `str(e)`; `error_handlers.py`'s 401/429/403
  handlers and `classify_http_error` have **zero production callers** (the
  live part is the OAuth-callback family, which classifies
  `OAuthFlowError`, not client exceptions).

## Decision

**Replace all 28 raw raises with `BaseAPIException` subclasses, keeping
status codes, details and headers byte-identical. No new FastAPI exception
handler**: because every replacement is an `HTTPException`, the built-in
handler renders the exact same response — the external API contract is
preserved *by construction*, not re-implemented. A decoupled plain-Exception
`ConnectorError` family was rejected: it would silently break both
`isinstance` paths, turn propagated errors into 500s via
`ErrorHandlerMiddleware`, and contradict ADR-002/023/108.

Mapping (8 categories → 28 sites):

| Category | Exception | Notes |
|---|---|---|
| 401 provider auth | `AuthenticationError` | detail via `APIMessages.connector_auth_invalid()` (was inline French, byte-identical in `fr`); keeps `X-Requires-Reconnect: true` |
| Upstream error passthrough | `ConnectorAPIError` (**new**) | upstream status forwarded unchanged (≥400; includes 5xx on the no-retry Routes/Geocoding paths) |
| Client-side rate limit | `RateLimitError` | legacy detail kept via new `detail` override |
| Circuit open | `ExternalServiceError(error_type="circuit_open")` | keeps `Retry-After` header |
| Network exhaustion | `ExternalServiceError(error_type="connection_error")` | |
| Retry exhaustion | `ExternalServiceError(error_type="max_retries")` | see divergence below |
| Missing config/API key | `ExternalServiceError(error_type="configuration_missing")` | |
| Domain 400/404 (credentials, connector, task list, matrix cap) | `ValidationError` / `ResourceNotFoundError` | |

Core extensions (all backward-compatible): `BaseAPIException`,
`AuthenticationError` and `ExternalServiceError` gain a `headers` param
(previously raw-HTTPException-only headers were impossible to express);
`RateLimitError` gains a `detail` override; `ConnectorAPIError` is the one
new class (dynamic upstream status — no existing class accepted one).

**Documented divergence from ADR-108**: retry exhaustion in the OAuth bases
raises `ExternalServiceError` (503), **not** `MaxRetriesExceededError`
(plain Exception). F0 verified its delta against 3 low-fan-out clients; the
OAuth bases feed every Google/Microsoft tool **and** REST routes
(`/connectors/{id}/calendars`, `/task-lists`) where a plain Exception would
become a 500 through `ErrorHandlerMiddleware` instead of today's 503.

**Pre-existing quirk kept as-is (both here and in ADR-108's base)**: the
`_on_rate_limit_exceeded()` 429 raised inside `_rate_limit()` is swallowed
by the caller's Redis-fallback `except Exception` and degrades to local
throttling — the 429 never propagates. Changing that is a behavior change,
out of scope; documented so nobody "fixes" it accidentally during a review.

Included hardenings (arbitrated): Microsoft's 401 message aligned on the
Google wording via `APIMessages` (provider-parity rule; gains the
reactivation sentence); upstream response bodies embedded in details
truncated to 200 chars (places/routes — PII/token hygiene); GPS coordinates
moved from ERROR/WARNING/INFO logs to DEBUG in the geocoding paths (no-PII
rule).

## Consequences

- Rule #18 holds in the whole client layer (`grep "raise HTTPException"
  src/domains/connectors/clients/` → 0); every client error now carries
  automatic structured logging + `http_errors_total` /
  `external_service_errors_total` metrics (new, intentional observability
  gain — log events are not API contract).
- Tool paths unchanged: `handle_tool_exception` still yields
  `INTERNAL_ERROR` with the same `str(e)` format (`"401: <detail>"` — the
  Starlette `__str__` is inherited); only the `error_type` metadata label
  changes (nothing keys on `"HTTPException"`, verified repo-wide). Briefing
  fetchers, `routes_tools` closed except-tuples, and the OAuth-callback
  classification are untouched.
- Existing `pytest.raises(HTTPException)` tests stay green by inheritance.
- Out of scope, intentionally: the 35 raw raises in routers/services
  (`llm_config` ×14, `health_metrics` ×5, `heartbeat` ×3, `user_mcp` ×4, …)
  — right layer, wrong idiom — are phase 2; the dead 401/429/403 handlers in
  `error_handlers.py` are an S7 candidate; passing the user's language to
  `connector_auth_invalid()` (clients don't know it — defaults to `fr`, as
  before) is deferred.

## Verification

`tests/unit/connectors/test_connector_client_error_contract.py` (34 tests)
pins the three invariants: per-site mapping — **all 28 migrated sites
individually exercised** (type + status + detail byte-identical + headers),
FastAPI edge parity (each typed exception rendered against its
raw-HTTPException twin via `TestClient` — same status, same JSON, same
headers), and tool-path classification. Full gates: 490
connector unit tests + 611 tools/heartbeat + briefing/users/core suites
green verbatim; ruff/black/mypy strict green on all touched files (one
pre-existing mypy invariance issue in `raise_invalid_credentials` surfaced
by the new `headers` param, fixed with an explicit `dict[str, Any]`
annotation); fast unit suite + fresh Docker boot to healthy.
