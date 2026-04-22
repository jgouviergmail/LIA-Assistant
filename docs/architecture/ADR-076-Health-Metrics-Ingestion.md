# ADR-076: Health Metrics Ingestion via Per-User Tokens

**Date**: 2026-04-20
**Status**: Accepted
**Revised**: 2026-04-21 — polymorphic samples + batch upsert (iPhone Shortcuts constraint)
**Revised**: 2026-04-22 — assistant integrations (agents + Heartbeat + journal + memory) + central `HEALTH_KINDS` registry for extensibility (v1.17.2)
**Context**: Expose authenticated REST endpoints so an iPhone Shortcut can POST **daily batches** of heart-rate and step samples, persist them per-user in PostgreSQL, surface them in the Settings UI as hour/day/week/month/year charts, and (v1.17.2) expose them to LIA's three central loops — conversation (LangGraph agents), proactivity (Heartbeat), and introspection (journal + memory) — behind a per-user opt-in.

## Context

The original design assumed the Shortcut could push **hourly** single-sample payloads. That turned out to be unworkable: iOS requires the iPhone to be unlocked to run time-based automations reliably, which the user cannot guarantee every hour. The pragmatic iOS pattern is therefore to batch the day's samples and let the Shortcut fire when the device is unlocked — possibly re-sending samples already sent earlier.

The Shortcut cannot carry a session cookie, so regular cookie-based auth is not usable. Passing the `user_id` in the query string was considered and rejected: a user ID is an **identifier** (visible in URLs, JWT payloads, logs, screenshots, emails); it is not a **secret**. Using it as an auth factor would let anyone who has seen the ID inject data on behalf of that user.

Additionally, iOS Shortcuts emits JSON in several inconsistent shapes depending on how the Raccourci is authored (Dictionnaire vs Texte vs Liste). The server cannot impose a single canonical shape without making the Shortcut authoring burdensome.

## Decision

Introduce a dedicated `health_metrics` DDD domain with:

### 1. Per-user ingestion tokens (secret, revocable, scoped)

- `health_metric_tokens` table with SHA-256 hashed tokens (`token_hash`), an 11-char display prefix (`hm_xxxxxxxx`), optional user label, and revocation timestamp.
- A user may hold N tokens simultaneously (rotation use case); each token is revoked independently. The raw value is returned exactly once at creation time through the UI and never again (same pattern as typical GitHub / Stripe PATs).
- The **same token** authenticates both ingestion endpoints (`/steps` and `/heart_rate`). Tokens cannot read user data, update settings, or drive any other API.

### 2. Two per-kind ingestion endpoints

- `POST /api/v1/ingest/health/steps` — batch of step samples
- `POST /api/v1/ingest/health/heart_rate` — batch of heart-rate samples
- `Authorization: Bearer hm_xxx` header, or the bare token (extra lenience for Shortcut editors).
- Each sample carries its own `date_start` / `date_end` (ISO 8601 with TZ offset). The server UTC-normalizes and second-truncates before storage. There is no server-side timestamp — the measurement window is always client-supplied.
- Per-token sliding-window rate limit (60 req/h default, configurable) backed by the existing `RedisRateLimiter`. Raised from the original 5/h to absorb burst traffic when the iPhone unlocks after a gap.

### 3. Flexible body parser

`parser.parse_samples_body()` accepts four envelope shapes:

1. Canonical JSON array
2. NDJSON (one JSON object per line)
3. `{"data": [...]}` wrapper
4. iOS Shortcuts "Dictionnaire" wrapping: `{"<ndjson_blob>": {}}` — detected by a heuristic (single key with embedded newlines + empty value)

The parser flattens all four to a `list[dict]` before validation. Malformed bodies return `400`; over-sized batches return `413` (`health_metrics_max_samples_per_request`, default 1000).

### 4. Polymorphic single-table storage

`health_samples` is a **single row per sample** table with a `kind` discriminator:

```
health_samples(id, user_id, kind, date_start, date_end, value, source, created_at, updated_at)
  CheckConstraint(kind IN ('heart_rate', 'steps'))
  UniqueConstraint(user_id, kind, date_start, date_end)  -- idempotency anchor
  Index(user_id, kind, date_start)                       -- list/aggregate driver
```

Rationale for polymorphic-single-table vs one-table-per-kind:
- Future extensibility (sleep, SpO2, calories) reduces to adding a new `kind` value plus validation/aggregation branches — no new table, no new endpoint.
- Aggregation over multiple kinds (HR avg and steps sum per day) traverses a single sorted scan instead of joining two streams.
- DRY: one set of migrations, one index, one deletion contract.

The downside — different kinds sharing a single `value INT` column — is acceptable because every physiological scalar we plan to onboard fits in an int.

### 5. Upsert idempotency (last-wins)

The unique constraint `(user_id, kind, date_start, date_end)` is the idempotency key. Re-sending a batch (e.g., the Shortcut resends the day so far) updates existing rows in place and does not create duplicates. `repository.upsert_samples()` uses PostgreSQL's `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING (xmax = 0) AS inserted` to discriminate inserts from updates in a single round-trip and expose both counts in the response.

### 6. Mixed per-sample validation

Out-of-range or malformed samples are **individually rejected** with their 0-based index, while valid siblings persist. Example response:

```json
{"received": 24, "inserted": 20, "updated": 4, "rejected": [{"index": 7, "reason": "out_of_range:above_max"}]}
```

This is the pragmatic middle ground between:
- **Strict whole-batch rejection** (drops 23 valid samples because one sensor glitched).
- **Fully tolerant** (pollutes the DB with impossible values).

Rejection reasons: `out_of_range`, `malformed`, `missing_field`, `invalid_date` — low-cardinality enough to use as Prometheus labels.

### 7. Aggregation in Python, not SQL

Each step sample's `value` is the count for the inter-sample window — bucket aggregation is a simple SUM. Heart rate is averaged (plus min/max). Doing the bucketing in Python keeps the gap-preserving semantics straightforward and stays orders-of-magnitude cheaper than going round-trip through SQL on the volumes involved (a few thousand points per user per year at most).

### 8. Gap-preserving charts

The aggregator emits **one point per bucket slot** in the requested window, with `has_data=False` for empty slots. `recharts` renders gaps natively with `connectNulls={false}`. This is honest about missing data (Shortcut did not fire for an hour) without client-side gap detection.

### 9. Deletion scope matches GDPR right-to-erasure

- `DELETE /health-metrics?kind=heart_rate|steps` — DELETE every row of the given kind.
- `DELETE /health-metrics/all` — DELETE every row. Tokens are left active (the user keeps the ability to continue ingesting).
- `ON DELETE CASCADE` on the FK to `users` covers full-account erasure automatically.

Note the departure from the original design: deletion is now row-scoped by `kind`, not column-scoped by `field` (there are no longer multiple value columns to NULL-out).

### 10. Feature flag gating

`HEALTH_METRICS_ENABLED` toggles the entire domain: routers are registered only when the flag is on. Default `False`; enabled in dev for development but not yet in prod until the iPhone flow is validated end-to-end.

## Consequences

### Positive

- **Security**: tokens are bound to a single scope (health ingestion), rotatable, revocable, and replaceable if leaked — unlike user IDs.
- **Data quality**: mixed validation gets the most out of every Shortcut fire, even when a sensor glitches.
- **iOS-realistic**: batch upsert matches how iOS Shortcuts actually behave (one fire per unlock). Re-sends are free.
- **Extensible**: a future `spo2` or `sleep` kind lands without a migration.
- **Observability from day one**: Prometheus counters split by `(kind, operation)` + a dedicated Grafana dashboard (21) cover insert/update ratios, latency, validation rejections, auth/rate-limit failures, token lifecycle, and deletions.

### Negative / trade-offs

- **One value column**: the polymorphic table limits the design to scalar measurements. A future `workout` kind carrying multiple scalars would need JSON or a second table. Accepted — not on the roadmap.
- **Batch size cap**: `health_metrics_max_samples_per_request` (default 1000) draws a line somewhere. It is parameterized specifically so a prolific user can raise it. Over-sized batches return `413` with a clear message.
- **Parser heuristics**: the iOS Shortcuts wrapping detection is a heuristic (single dict key + newline-in-key + empty value). If iOS ever changes shape, we will need another branch. The NDJSON fallback catches most degenerate cases.

## Privacy by design

Health data is a "special category" under GDPR article 9. Mitigations baked into the design:

- **Encryption at rest**: standard PostgreSQL DB-level encryption. No applicative encryption (`encrypt_data`) on heart rate / steps — numeric scalars are low-sensitivity compared to PII text, and encryption-at-rest on the DB volume is already in place.
- **Tokens hashed**: the raw token never hits the DB; the display prefix only is non-secret.
- **Log hygiene**: structured logs carry `user_id`, `kind`, `source`, counts, but never raw per-sample values — logs are not a duplicate storage tier.
- **Rate limit**: 60 req/h/token blocks scraping and spam while accommodating legitimate burst re-sends.
- **User-controlled deletion**: per-kind or total, via the Settings UI, with `ON DELETE CASCADE` tying it to account erasure.

## Related

- ADR-017: Rate-limiting architecture (reused `RedisRateLimiter`).
- ADR-073: Last-known location persistence (similar sensitivity framing).
- Config pattern: `src/core/config/health_metrics.py` follows the module-split convention established by ADR-009.

## v1.17.2 revision — Assistant integrations + extensibility

The v1.17.1 decisions (polymorphic samples, batch upsert, mixed validation,
gap-preserving charts) are preserved unchanged. The 2026-04-22 revision
adds four downstream integrations and a central registry making future
kinds (sleep, SpO2, calories) cheap to onboard.

### 11. Central `HEALTH_KINDS` registry

`src/domains/health_metrics/kinds.py` is now the **single source of
truth** for per-kind semantics: physiological bounds, intra-batch merge
strategy, bucket aggregation method, baseline kind (`daily_sum` /
`daily_avg` / `resting`), owning agent name, UI i18n key, and the legacy
response fields consumed by `HealthMetricAggregatePoint`. Ingestion
validation, repository merge, aggregator, baseline, signal detection,
heartbeat, memory, and journal pipelines all consume this registry —
adding a new kind is a single-file edit plus a per-kind tool pack (see
[`docs/technical/HEALTH_METRICS.md`](../technical/HEALTH_METRICS.md)).

### 12. Adaptive baseline (`bootstrap` → `rolling`)

`baseline.compute_baseline()` selects between a bootstrap median (< 7
days of history, surfaced with `mode="bootstrap"` so the LLM qualifies
its statements) and a rolling 28-day median (`mode="rolling"`). Backing
settings: `HEALTH_METRICS_BASELINE_MIN_DAYS`,
`HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS`.

### 13. Factual signal detection

`signals.detect_recent_variations()` + `signals.detect_notable_events()`
emit **facts, not diagnoses**: directional streaks above the configured
daily delta threshold for `HEALTH_METRICS_VARIATION_MIN_DAYS`
consecutive days, and structural events (inactivity streaks on steps).
Thresholds are parameterized.

### 14. Single `health_agent` with seven hand-crafted tools

One agent ↔ one domain, matching the convention used across the codebase
(`email_agent`, `event_agent`, `weather_agent`…). Seven tools grouped
under `health_agent` — steps summary / breakdown / baseline delta, heart
rate summary / baseline delta, cross-kind overview / change detection —
registered in the planner catalogue behind the `HEALTH_METRICS_ENABLED`
flag. Each tool gates on `User.health_metrics_agents_enabled` at entry
via `_check_user_toggle_or_error`, returning
`UnifiedToolOutput.failure(error_code="PERMISSION_DENIED")` when the
user has not opted in.

**Time-windowed queries** (`time_min` / `time_max` ISO 8601) — same
pattern as `calendar_tools.search_events_tool` and
`emails_tools.search_emails_tool`. The QueryAnalyzer pre-resolves
temporal references ("this week" → "2026-04-20 to 2026-04-26") in its
`resolved_references` mapping, and the planner splits the two dates
across the two tool parameters. Defaults on omission: `time_min` →
today 00:00 UTC, `time_max` → `datetime.now(UTC)`. Tools for
trend-over-days (`get_steps_daily_breakdown_tool`,
`compare_*_to_baseline_tool`, `detect_health_changes_tool`) use a
simpler integer `days` / `window_days` parameter.

**Factual figures inlined in the `message` field** — all numeric values
(totals, averages, per-day entries) are rendered into the
`UnifiedToolOutput.message` text so the Response LLM surfaces them
without reaching for `structured_data` (pattern from `weather_tools`).
This avoids the "data details lost to the LLM" failure mode where only
a summary sentence like "8 days with data" would reach the response
node.

### 15. Heartbeat source `health_signals`

`context_aggregator._fetch_health_signals()` injects a compact payload
(summary-today + baseline deltas + recent variations + notable events)
into the Heartbeat `CURRENT CONTEXT`. Capped by a 2-second
`asyncio.wait_for` — timeout / error → silent `None` so the heartbeat
never blocks on health data.

### 16. Memory biometric enrichment (`context_biometric` JSONB)

New optional `memories.context_biometric` column (migration
`health_metrics_005`). The memory extractor injects a
`{health_context}` block into the prompt and asks the LLM to emit a
compact `context_biometric` blob when the memory carries a significant
emotional weight. Stored blob = deltas / trends / events only — never
raw sensor values.

### 17. Journal context injection

Both `{health_context}` (extraction) and `{health_signals_section}`
(consolidation) are injected only when the user has opted in. The
consolidation's analyst persona is instructed to enrich its reflections
factually without reproducing raw values.

### 18. Single per-user toggle

`User.health_metrics_agents_enabled` (migration `health_metrics_004`,
default `false`, opt-in) gates all four integrations at once. One
interrupt for the user, mirrored in the pattern of `memory_enabled`
and `journals_enabled`. Endpoint
`PATCH /auth/me/health-metrics-agents-preference`.

### Privacy framing reinforced

- **Never raw values in downstream artifacts**: `context_biometric`,
  heartbeat `health_signals`, and prompt-injected `health_context` all
  carry deltas / trends / events only. Raw integers stay in
  `health_samples` where GDPR erasure applies.
- **Opt-in by default**: the 4-integration toggle defaults to `false`.
- **Feature flag gates DB migration side-effects**: `health_metrics_004`
  adds a NOT NULL boolean with `server_default=false` so existing rows
  keep the safe default.

## Open items

- A lightweight export-to-CSV action may be added to the Settings UI if the data-portability requirement is raised.
- Resting-HR baseline (currently `BaselineKind.RESTING` = placeholder min-per-day) becomes meaningful once a future `sleep_duration` kind lands and unlocks sleep-aware filtering.
