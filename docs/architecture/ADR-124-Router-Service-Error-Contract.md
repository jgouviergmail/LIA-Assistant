# ADR-124: Router/Service Domain Error Contract — Eliminating Raw HTTPException Raises (Rule #18 Phase 2)

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-002](ADR-002-Unified-Error-Handling.md) (BaseAPIException taxonomy), [ADR-114](ADR-114-Connector-Client-Domain-Error-Contract.md) (phase 1 — connector client layer), [ADR-117](ADR-117-Background-Chat-Runs.md) (active-run lock 409)

## Context

ADR-114 eliminated the 28 raw `fastapi.HTTPException` raises of the connector
client layer and explicitly deferred "the 35 raw raises in routers/services —
right layer, wrong idiom" to a phase 2. Inventory at migration time
(2026-07-10): **33 real raise sites across 13 files** (+1 anti-pattern usage
example in the `i18n_api_messages` module docstring) — `reasoning_validation`
×7, `llm_config/router` ×5, `health_metrics/ingest_router` ×5, `llm_config/
service` ×2, `user_mcp/admin_router` ×3, `heartbeat/router` ×3, `agents/api/
router` ×2, plus 6 single sites (user_mcp OAuth 502, auth tombstone 410, auth
rate limiter 429, connectors photo proxy 400, scheduled_actions 409, channels
webhook 403). Raw raises are untyped, invisible to Prometheus, unlogged by
the central mechanism, and violate review rule #18.

Notable stale claim removed: `ingest_router` justified its raw 401s with a
comment stating centralized raisers "do not propagate the WWW-Authenticate
challenge header" — false since ADR-114 added the `headers` param to
`AuthenticationError`/`BaseAPIException`.

## Decision

**Replace all 33 sites with centralized raisers / `BaseAPIException`
subclasses from `src/core/exceptions.py`, keeping status codes, details and
headers byte-identical** (same "preserved by construction" argument as
ADR-114: every replacement IS-A `HTTPException`, so FastAPI's built-in
handler renders the exact same response).

Core extensions (all in `src/core/exceptions.py`):

| Addition | Kind | Serves |
|---|---|---|
| `StructuredValidationError` + raiser | 422, Pydantic-style dict detail (`type/loc/msg/input/ctx`) | reasoning_validation ×7, llm_config service ×2 |
| `UnprocessableEntityError` + raiser | 422, plain-string detail | heartbeat min>max |
| `PayloadTooLargeError` + raiser | 413 (no class existed) | ingest batch cap |
| `BadGatewayError` + raiser | 502 (no class existed; ≠ 503 `ExternalServiceError`) | user_mcp OAuth initiate |
| `GoneError` | 410, dict-capable detail | auth `/refresh` tombstone |
| `RateLimitError` | gains `headers` + dict-capable `detail` (raiser gains both, backward-compatible) | ingest / auth deps / HITL 429s with `Retry-After` |
| `ResourceConflictError` | gains dict-capable `detail` | active-run lock 409 |
| Raisers: `raise_bearer_auth_failed`, `raise_admin_mcp_server_not_found`, `raise_llm_type_not_found`, `raise_scheduled_action_already_executing`, `raise_run_in_progress`, `raise_invalid_webhook_signature` | thin wrappers over existing classes | remaining sites |

Dict-capable details follow the established `ConnectorValidationError`
pattern (str passed to the base for logging, dict overriding `self.detail`
on the wire). New 422/413 classes use the non-deprecated Starlette constants
(`HTTP_422_UNPROCESSABLE_CONTENT`, `HTTP_413_CONTENT_TOO_LARGE` — same
numeric values).

**File-size ratchet arbitration**: `core/exceptions.py` was 909 logical SLOC
under a frozen 928 cap — ~130 SLOC of additions did not fit. Resolution
(approved): extract `BaseAPIException` to the internal module
`src/core/_exceptions_base.py` and the bounded-context families (memory
store, interests, STT, WebSocket) to `src/core/exceptions_domains.py`, both
re-exported from `src/core/exceptions.py` (explicit `as` aliases) — **the
façade keeps every consumer import unchanged** and avoids the circular
import a bottom-of-module re-export would create. Result: 801/928 SLOC after
additions; new modules 68 and 189 SLOC (< 600 global ceiling); cap lowered
via `task ratchet:update`.

**One deliberate contract change (user-approved)**: the heartbeat
"min > max" 422 guard was raised inside a `try` whose `except Exception`
degraded it to a generic 500 — the pre-migration observable contract was
500. An `except HTTPException: raise` arm (standard idiom, cf.
`auth/router.py`) now lets the 422 reach the client as intended; being now
user-visible, its detail goes through `APIMessages.heartbeat_min_max_invalid`
(6 languages via the `normalize_language` chokepoint; the English wording
keeps the endpoint's historical text). Every other site is byte-identical.

**HITL 429 site — real contract clarified**: the raise lives inside the SSE
`event_generator`, AFTER the response has started; it has therefore never
reached the client as an HTTP 429 — the generator's `except Exception`
converts it into an SSE `error` event (message from
`SSEErrorMessages.stream_error`, classified "transient") + a `done` chunk.
The site's misleading "Raise HTTP 429" comment was fixed. Classification is
unchanged by the migration: `str(e)` is identical by Starlette `__str__`
inheritance ("429: {...rate_limit_exceeded...}", already matching the
transient keywords), and the typed name `RateLimitError` is itself in the
classifier's transient set. Only the `sse_streaming_errors_total` label moves
from `HTTPException` to `RateLimitError` (no alert/dashboard keys on the old
value — alerts aggregate, the dashboard groups dynamically).

**Chaining note**: raisers do not take a cause, so six `raise ... from e`
sites lose the explicit `__cause__`; the implicit `__context__` is preserved
during exception handling — API contract unaffected, log tracebacks still
show the original error.

## Consequences

- Rule #18 now holds in the WHOLE backend: `grep "raise HTTPException"
  apps/api/src/` → **0 hits, no exemptions** (`core/exceptions.py` itself
  subclasses, never raises raw). Every migrated error now carries automatic
  structured logging + `http_errors_total` metrics (intentional
  observability gain — log events are not API contract, ADR-114 precedent).
- All classification surfaces survive by inheritance, verified: 4
  `except HTTPException` sites (auth router ×2, auth deps fail-open,
  connectors photo proxy) and 2 `isinstance(e, HTTPException)` paths
  (`users/service.py`, `agents/tools/runtime_helpers.py`), plus the
  boot-time catch in `bootstrap.validate_llm_defaults_against_matrix` and
  the non-raising twin `reasoning_effort_matches_widget`.
- Non-recurrence guard: the `code-hygiene` CI job gains a "Check for raw
  HTTPException raises" grep step — `::warning` for one release to absorb
  in-flight branches, then to be flipped to `::error` + `exit 1`.
- The `i18n_api_messages` module docstring no longer teaches the
  anti-pattern (usage example now shows `ResourceNotFoundError`).

## Verification

`tests/unit/core/test_router_service_error_contract.py` (42 tests) pins the
invariants, reproducing the ADR-114 method: per-site mapping — **every site
was first pinned against the PRE-migration behavior with
`pytest.raises(HTTPException)` (33/33 green before any code change), then
strengthened to the typed exception after migration** (status + detail +
headers byte-identical, carried by inheritance); FastAPI edge parity (each
new class rendered against its raw-HTTPException twin via `TestClient` —
same status, same JSON, same headers, including `Retry-After` and
`WWW-Authenticate: Bearer`); the HITL 429 exercised END-TO-END through the
real SSE generator (retry preamble → `error` event with the classifier's
exact message → `done` chunk) plus a classification-parity proof
(`stream_error(legacy) == stream_error(typed)` across all 6 languages); the
heartbeat 422 localization verified per-language including the `zh` →
`zh-CN` normalization chokepoint (the new `APIMessages` table is also
auto-covered by the backend i18n parity AST guard). Full gates: fast unit
suite green (9138), integration suite green (138), ruff/black/mypy green on
the whole backend, file-size ratchet green with the lowered caps (928→848,
784→780), Docker dev boot verified healthy.
