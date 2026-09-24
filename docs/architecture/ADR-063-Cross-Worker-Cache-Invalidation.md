# ADR-063: Cross-Worker Cache Invalidation via Redis Pub/Sub

**Status**: ✅ IMPLEMENTED (2026-03-24) — amended 2026-09-23 (the pricing cache's writers publish, see the end)
**Author**: Claude Code (Opus 4.6)

## Context

LIA runs with `uvicorn --workers 4` (multiprocessing). In-memory caches (class-level
and module-level variables) are isolated per process. When an admin modifies a config
via the API, `invalidate_and_reload()` only updates the cache in the worker that handled
the HTTP request — the other 3 workers keep serving stale data.

**Bug observed**: Changing the Initiative Node LLM model from `gpt-5-mini` to `gpt-5-nano`
via the admin UI was only effective for ~25% of requests (1 worker out of 4).

### Affected Caches

| Cache | File | Runtime Modification |
|-------|------|---------------------|
| `LLMConfigOverrideCache` | `domains/llm_config/cache.py` | Admin LLM config PUT/DELETE |
| `SkillsCache` | `domains/skills/cache.py` | Admin skill CRUD endpoints |
| `GoogleApiPricingService` | `domains/google_api/pricing_service.py` | Admin pricing reload |
| `PricingCacheService` | `infrastructure/cache/pricing_cache.py` | Admin LLM pricing CRUD, workbook import, cache reload, USD→EUR rate writes — admin route and daily sync (since 2026-09-23 — see the amendment) |
| `ModelCapabilitiesCache` | `infrastructure/llm/model_capabilities_cache.py` | Admin LLM pricing/capabilities CRUD (ADR-078) |
| `ImageOptionsCache` | `domains/image_generation/options_cache.py` | Admin image pricing CRUD (ADR-078) |

## Decision

Use **Redis Pub/Sub** for cross-worker cache invalidation. A single Redis channel
broadcasts invalidation events to all worker processes.

### Pattern: `load_*()` vs `invalidate_and_reload()`

Each cache exposes two levels:

1. **`load_*()`** — Raw reload from source (DB/disk). No publish. Used at startup
   and by the pub/sub subscriber.
2. **`invalidate_and_reload()`** — Calls `load_*()` then publishes to Redis. Used
   by services/routers at runtime.

The subscriber only calls `load_*()`, making infinite loops impossible.

### Architecture

```
Service calls invalidate_and_reload()
  ├── 1. load_from_db()        → local reload
  └── 2. publish(name, pid)    → Redis channel "cache:invalidation"
                                       │
                   ┌───────────────────┤
                   ▼                   ▼
             Worker B subscriber  Worker C subscriber
             (pid ≠ publisher)    (pid ≠ publisher)
             → load_from_db()    → load_from_db()

                   ▼ (also received by)
             Worker A subscriber (publisher)
             (pid == publisher → SKIP)
```

### Key Files

- **`src/infrastructure/cache/invalidation.py`** — Centralized module: registry,
  publisher, subscriber, startup verification.
- **`src/core/constants.py`** — `REDIS_CHANNEL_CACHE_INVALIDATION` and `CACHE_NAME_*`
  constants.

## Consequences

### Positive

- **Transparent**: publish is inside `invalidate_and_reload()`, not in callers.
  Developers don't need to think about cross-worker invalidation.
- **Instant**: Redis pub/sub, not polling.
- **Resilient**: Redis down = warning log, no crash. The local worker already reloaded.
- **Startup verification**: `verify_registry_completeness()` logs an error if a known
  cache has no registered handler.

### Negative

- A developer creating a brand-new in-memory cache must follow the pattern
  (register in lifespan, add `invalidate_and_reload()` method). This is documented
  but not enforced by the type system.

## How to Add a New Cache

1. Add a `CACHE_NAME_*` constant to `src/core/constants.py`.
2. Add `invalidate_and_reload()` to your cache class that calls `load_*()` then
   `await publish_cache_invalidation(CACHE_NAME_*)`.
3. Register a reload handler in `src/main.py` lifespan via `register_cache()`.
4. Add the constant to `verify_registry_completeness()` expected set.

## Amendment 2026-09-23 — a registered handler with no caller

The table above filed `PricingCacheService` as « startup only (prepared for
future) ». It was not: the admin reload endpoint already rebuilt it through
`refresh_from_database()`, the RAW load, and the ADR-078 admin endpoints
(2026-05-05) added `_invalidate_caches`, which did the same after every tariff
create, update and deactivation — the path ADR-223's windows and ADR-228's
workbook import later rode on. The handler was registered,
`verify_registry_completeness()` was green, and the only
`publish_cache_invalidation("pricing")` in the codebase sat in
`invalidate_and_refresh()`, which nobody called: under `--workers 4` an edited
tariff reached one worker in four, and the three others billed the old price
until they restarted — the defect this ADR was written to close, left open on
the one cache marked « prepared ».

The cache also holds the USD→EUR rate every cached cost is converted with,
and its two writers — `POST /admin/llm/currencies` and the daily
`sync_currency_rates` job — published nothing either and did not even rebuild
their own worker: a synced rate reached no worker's costs before it restarted.

Every writer of a table this cache holds now calls
`refresh_and_publish_pricing_cache()` AFTER its commit — `invalidate_and_refresh()`
underneath: rebuild, then publish, never publish after a failed rebuild. The
rebuild reads through a session of its own, so before the commit it would
publish the state being replaced. Two precisions on the pattern this cache now
follows, both measured on Docker dev (ADR-223 amendment):

- **Startup rebuilds from the source, never from a shared blob.** The pricing
  cache used to start from its Redis blob when one existed, and a blob written
  before a deploy's migration carries the old rows for its whole TTL — while a
  worker keeps what it loaded for its whole life. Only the subscriber adopts the
  blob (`load_published_pricing_cache`), because the notifying worker
  republished it just before publishing — and a startup whose database read
  fails, since an older tariff prices better than zero for the worker's life.
- **A reload never empties the local copy first.** The explicit reload used to
  clear the cache, then rebuild: a rebuild that failed left the worker pricing
  every call at zero.

Pinned by `tests/integration/test_llm_admin_routes.py` (a tariff update, the
reload and a new exchange rate each publish the pricing invalidation),
`tests/unit/infrastructure/scheduler/test_currency_sync.py` (the synced rate is
published once committed, a failed fetch publishes nothing) and
`tests/unit/infrastructure/test_pricing_cache_startup.py`.

## References

- `src/infrastructure/cache/invalidation.py` — full implementation
- `tests/unit/infrastructure/cache/test_invalidation.py` — unit tests
