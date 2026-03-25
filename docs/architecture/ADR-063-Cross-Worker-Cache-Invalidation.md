# ADR-063: Cross-Worker Cache Invalidation via Redis Pub/Sub

**Status**: ✅ IMPLEMENTED (2026-03-24)
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
| `PricingCacheService` | `infrastructure/cache/pricing_cache.py` | Startup only (prepared for future) |

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

## References

- `src/infrastructure/cache/invalidation.py` — full implementation
- `tests/unit/infrastructure/cache/test_invalidation.py` — unit tests
