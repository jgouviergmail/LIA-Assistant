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

## Amendment 2026-10-13 — a provider's 429 is backpressure on one key, never the service's health

Measured on dev, 2026-10-13: three delegated research runs of one account (78
Brave and Perplexity calls in twenty minutes, on that account's own keys, nothing
else using them) drew their first 429s on their first parallel round of three or
four searches — a per-second limit, not a quota: every retry one or two seconds
later passed. But the client counted each 429 as a FAILURE of the breaker every
account shares (`apikey_{connector}`): it opened on the third, re-opened at each
half-open probe, and refused 13 of the 15 searches one run lost, which the expert
read as « service temporarily unavailable » and the person as « web search
degraded ». The nine Perplexity failures were moreover counted as successes:
`APIKeyConnectorTool.handle_error` returned a JSON string, which the one success
predicate reads as a success (ADR-303).

- **A 429 is recorded as an answer** (`record_success`): the breaker measures the
  service's health (5xx, network errors, malformed bodies), and a limit on one key
  says nothing of it. The same holds for the instance key the system geocoding path
  passes.
- **Its retries are jittered, bounded and its own**: the provider's `Retry-After`,
  else the exponential step, plus up to one second drawn at random (never earlier
  than asked) — the siblings of one parallel round drew their 429 on the same tick
  and retried on the same one. A 429 is waited out in a loop of its own
  (`_send_through_rate_limits`) under `API_KEY_CLIENT_RATE_LIMIT_ATTEMPTS`, apart
  from the call's `max_retries`, which keep bounding the failures that may cost a
  whole network timeout each (5xx, malformed bodies, network errors). A
  `Retry-After` above `API_KEY_CLIENT_RETRY_AFTER_MAX_SECONDS` is handed back at once
  rather than waited out inside the caller's own timeout. Simulated against a
  provider serving one request per second per key, four rounds of four parallel
  searches: 5 of 16 answered before (10 refused by the breaker), 12 of 16 with three
  attempts, 16 of 16 with four — a one-off measurement on 2026-10-13, not a guard:
  an httpx `MockTransport` answering 429 past one request per rolling second, four
  rounds of four concurrent `_make_request` three seconds apart, HEAD's module
  loaded from git beside the working tree's. The price is the wait: about five
  seconds more per round of four against such a key, where the lost searches cost
  the model a whole round to redo them.
- **The backoff precedes a retry, never follows the last attempt**: every failure
  branch slept its exponential step and then left the loop, so a 5xx or a
  malformed body on the last attempt delayed the failure by 4 s for nothing (the
  429 branch did the same). The sleep now opens the next attempt. The verb
  dispatch, the breaker check and records and the parameter merge left the method,
  whose cyclomatic complexity fell from 32 to 12 (the backend ratchet from 290 to
  288 hotspots).
- **A spent 429 is typed**: `ConnectorAPIError(status_code=429)` with the delay in
  `Retry-After`, no longer `MaxRetriesExceededError` — so the tool layer reads
  `RATE_LIMIT_EXCEEDED` (and draws the rate-limit banner) and the briefing's
  weather card says « rate limit », never « network ». A circuit-open refusal
  carries its delay too.
- **An API-key tool fails by returning a failure**: in registry mode
  `handle_error` returns the `UnifiedToolOutput`, and a refusal the service side
  produced is said by its status in technical English, with our own exception's
  detail (bounded, what the JSON used to carry) and its delay
  (`runtime_helpers.describe_external_refusal`; retries that never got an answer
  are `EXTERNAL_API_ERROR`). A provider's own refusal (`httpx.HTTPStatusError`, a
  404 « city not found ») is said by its status too — never by its body, which is
  third-party text and would reach the model with our authority.
- **Brave has two doors**: the tool reads `search_or_raise`; `search` keeps its
  None-on-error contract for the interest sweep, the radio and the enrichment.

Guards: `tests/unit/connectors/test_base_api_key_client.py`
(`TestAProviderRateLimitIsBackpressure`), `test_api_key_tool_failures.py`,
`TestBraveRateLimitIsSaid`, `test_weather_error_classification.py`. Left as found,
and named here: the OAuth clients still count a 429 as a breaker failure — Google
and Microsoft quotas mix per-user and per-project limits, which needs its own
analysis; and the client shaper still counts per minute, so it cannot see a
per-second burst (ADR-254's trap): providers state their limits in different units
and a static rate cannot match every account's plan, so the jittered 429 path is
the adaptive one.
