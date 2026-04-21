# ADR-076: Health Metrics Ingestion via Per-User Tokens

**Date**: 2026-04-20
**Status**: Accepted
**Context**: Expose an authenticated REST endpoint so an iPhone Shortcut can POST hourly health metrics (heart rate, per-period step count, extensible payload), persist the samples per-user in PostgreSQL, and surface them in the Settings UI as hour/day/week/month/year charts. Set the foundation for a later LLM tool that lets the assistant reason over this data.

## Context

The user wants to push two metrics from iOS Shortcuts every hour:
- `c` — last heart rate sample (bpm)
- `p` — steps recorded since the previous sample (NOT a daily cumulative)

The Shortcut cannot carry a session cookie, so regular cookie-based auth is not usable. Simply passing the `user_id` in the query string was considered and rejected: a user ID is an **identifier** (visible in URLs, JWT payloads, logs, screenshots, emails); it is not a **secret**. Using it as an auth factor would let anyone who has seen the ID inject data on behalf of that user.

## Decision

Introduce a dedicated `health_metrics` DDD domain with:

### 1. Per-user ingestion tokens (secret, revocable, scoped)

- `health_metric_tokens` table with SHA-256 hashed tokens (`token_hash`), an 11-char display prefix (`hm_xxxxxxxx`), optional user label, and revocation timestamp.
- A user may hold N tokens simultaneously (rotation use case); each token is revoked independently. The raw value is returned exactly once at creation time through the UI and never again (same pattern as typical GitHub / Stripe PATs).
- Tokens authenticate a single endpoint (`POST /api/v1/ingest/health`). They cannot read user data, update settings, or drive any other API.

### 2. Ingestion endpoint

- `POST /api/v1/ingest/health` with body `{"data": {"c": int, "p": int, "o": str?}}`.
- `Authorization: Bearer hm_xxx` header, or the bare token (extra lenience for Shortcut editors).
- The server timestamps the sample at reception (`datetime.now(UTC)`). Clients do not supply a timestamp; this matches the "no batch / no retry" contract the user defined for the iOS side.
- Per-token sliding-window rate limit (5 req/hour default, configurable) backed by the existing `RedisRateLimiter`.

### 3. Mixed per-field physiological validation

Out-of-range values are **stored as NULL** with a warning log, while the rest of the payload is preserved. Example: `{"c": 0, "p": 4521}` ingests a row with `heart_rate=NULL`, `steps=4521`. This is the pragmatic middle ground between:

- **Strict rejection** (drops valid sibling fields when one sensor glitches).
- **Fully tolerant** (pollutes the DB and the charts with impossible values).

Bounds come from `settings.health_metrics_heart_rate_{min,max}` / `..._steps_{min,max}` and default to `[20, 250]` bpm / `[0, 15000]` steps per sample (per-sample upper bound = generous worst-case for one ingestion window, NOT a daily cap).

### 4. Storage model

`health_metrics` is a **single row per POST** table with nullable metric columns. A compound index on `(user_id, recorded_at)` supports all lookup shapes (listing, aggregation, deletion scope).

```
health_metrics(id, user_id, recorded_at, heart_rate, steps, source, created_at, updated_at)
```

Rationale for one-row-per-post vs one-row-per-metric:
- Every ingestion carries a bundle (HR + steps together).
- Mixed validation needs sibling-preservation, which is simpler when fields share a row.
- Future extensibility (sleep, SpO2, calories, …) adds nullable columns without migration of existing data.

### 5. Aggregation in Python, not SQL

Each sample's `steps` field is already the count for the inter-sample period — bucket aggregation is a simple SUM. Heart rate is averaged. Doing the bucketing in Python keeps the gap-preserving semantics straightforward and stays orders-of-magnitude cheaper than going round-trip through SQL on the volumes involved (a few thousand points per user per year at most).

### 6. Gap-preserving charts

The aggregator emits **one point per bucket slot** in the requested window, with `has_data=False` for empty slots. `recharts` renders gaps natively with `connectNulls={false}`. This is honest about missing data (Shortcut not sent for an hour) without client-side gap detection.

### 7. Deletion scope matches GDPR right-to-erasure

- `DELETE /health-metrics?field=heart_rate|steps` — UPDATEs the column to NULL across every row. Preserves the other columns.
- `DELETE /health-metrics/all` — DELETEs every row. Tokens are left active (user keeps the ability to continue ingesting).
- `ON DELETE CASCADE` on the FK to `users` covers full-account erasure automatically.

### 8. Feature flag gating

`HEALTH_METRICS_ENABLED` toggles the entire domain: routers are registered only when the flag is on. Default `False`; enabled in dev for development but not yet in prod until the feature is validated end-to-end with the iPhone Shortcut.

## Consequences

### Positive

- **Security**: tokens are bound to a single scope, rotatable, revocable, and can be fully replaced if leaked — unlike user IDs.
- **Data quality**: mixed validation gets the most out of every Shortcut trigger, even when a sensor glitches.
- **UX**: the Settings page ships with all four blocks (API, charts, stats, management) on day one, no external tool required.
- **Observability from day one**: 8 Prometheus metrics + a dedicated Grafana dashboard (21) already cover ingest throughput, latency, validation rejections, auth/rate-limit failures, token lifecycle, and deletion operations.

### Negative / trade-offs

- **Resolution**: one heart-rate point per hour is a coarse signal. Period-wide averages are averages of instantaneous samples rather than true physiological averages. Product-accepted — the frequency can be raised later without schema change.
- **Missed hours = missing data**: if an hourly Shortcut misses, the corresponding bucket simply has no sample (`has_data=False`). The chart shows a gap, no extrapolation.
- **No batch ingestion**: the Shortcut cannot catch up on missed hours. Confirmed as a product constraint.

## Privacy by design

Health data is a "special category" under GDPR article 9. Mitigations baked into the design:

- **Encryption at rest**: standard PostgreSQL DB-level encryption. No applicative encryption (`encrypt_data`) on heart rate / steps — numeric scalars are low-sensitivity compared to PII text, and encryption-at-rest on the DB volume is already in place.
- **Tokens hashed**: the raw token never hits the DB; the display prefix only is non-secret.
- **Log hygiene**: structured logs carry `user_id`, `source`, `status`, but never the raw metric values — logs are not a duplicate storage tier.
- **Rate limit**: 5 req/h/token blocks scraping and spam.
- **User-controlled deletion**: selective (per field) or total, via the Settings UI, with `ON DELETE CASCADE` tying it to account erasure.

## Related

- ADR-017: Rate-limiting architecture (reused `RedisRateLimiter`).
- ADR-073: Last-known location persistence (similar sensitivity framing).
- Config pattern: `src/core/config/health_metrics.py` follows the module-split convention established by ADR-009.

## Open items

- LLM tool exposure (assistant reasoning over the data) is out of scope for this ADR; it will be addressed separately once the data volume and usage patterns are visible.
- A lightweight export-to-CSV action may be added to the Settings UI if the data-portability requirement is raised.
