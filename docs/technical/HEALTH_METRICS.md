# Health Metrics — technical reference

Domain: `src/domains/health_metrics/`
Feature flag: `HEALTH_METRICS_ENABLED` (default `false`)
ADR: [ADR-076](../architecture/ADR-076-Health-Metrics-Ingestion.md)
User guide: [GUIDE_IPHONE_SHORTCUTS_HEALTH](../guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md)

## Purpose

Ingest **daily sample batches** from an iPhone Shortcut automation (heart rate and step counts, each sample carrying its own `date_start` / `date_end`), persist them per-user as **polymorphic** rows in a single table, and visualize them in the Settings UI at five period granularities.

The design intentionally avoids hourly push requirements (which would require a permanently unlocked iPhone). Instead, the client sends the full daily batch whenever the Shortcut runs, and the server upserts on `(user_id, kind, date_start, date_end)` — re-sends are idempotent and last-wins.

## Architecture at a glance

```
iPhone Shortcut
    │   POST /api/v1/ingest/health/steps       (Bearer hm_xxx, full day batch)
    │   POST /api/v1/ingest/health/heart_rate  (same Bearer, full day batch)
    ▼
ingest_router.py  ───────▶  auth + rate limit (Redis) + flexible parser
    │
    ▼
service.ingest_batch()  ──▶  per-sample validation (mixed — reject one, keep siblings)
    │
    ├─▶  health_samples UPSERT ON CONFLICT (user_id, kind, date_start, date_end)
    └─▶  last_used_at UPDATE on the token

Settings UI
    │   GET /api/v1/health-metrics/aggregate?period=…
    ▼
router.py  ─────────────▶  service.aggregate()
                                │
                                ▼
                          aggregator.aggregate_samples()
                          (polymorphic buckets — HR avg/min/max + steps sum)
```

## Database schema

### `health_samples` (polymorphic)

| Column        | Type          | Nullable | Notes                                                |
| ------------- | ------------- | -------- | ---------------------------------------------------- |
| `id`          | UUID PK       | No       | Generated                                            |
| `user_id`     | UUID FK       | No       | `users.id`, `ON DELETE CASCADE`                      |
| `kind`        | VARCHAR(16)   | No       | Discriminator: `heart_rate` or `steps`               |
| `date_start`  | TIMESTAMPTZ   | No       | Start of the measurement interval (UTC-normalized)   |
| `date_end`    | TIMESTAMPTZ   | No       | End of the measurement interval (UTC-normalized)     |
| `value`       | INTEGER       | No       | bpm for HR, count for steps                          |
| `source`      | VARCHAR(32)   | No       | Slugified origin label; default `'iphone'`           |
| `created_at`  | TIMESTAMPTZ   | No       | From `TimestampMixin`                                |
| `updated_at`  | TIMESTAMPTZ   | No       | From `TimestampMixin`                                |

Constraints:
- `CheckConstraint("kind IN ('heart_rate', 'steps')")` — defends against typos
- `UniqueConstraint(user_id, kind, date_start, date_end)` — idempotency anchor
- `Index(user_id, kind, date_start)` — drives listing + aggregation queries

### `health_metric_tokens`

Unchanged from the initial design: `id`, `user_id` (FK CASCADE), `token_hash` (SHA-256 hex, unique), `token_prefix` (display), `label`, `last_used_at`, `revoked_at`, timestamps. The raw token value is never stored — it is generated via `secrets.token_urlsafe` prefixed with `hm_`, returned once in the creation response, and from then on exists only as a SHA-256 hash.

## API surface

### Ingestion (token-auth)

- `POST /api/v1/ingest/health/steps` — Bearer `hm_xxx`. Body: batch of step samples.
- `POST /api/v1/ingest/health/heart_rate` — Same Bearer. Body: batch of heart-rate samples.

Each endpoint accepts **four envelope shapes** (see `parser.py`):

1. Canonical JSON array: `[{"date_start":"…","date_end":"…","steps":1234,"o":"iphone"}, …]`
2. NDJSON: one JSON object per line
3. `{"data": [...]}` envelope
4. iOS Shortcuts "Dictionnaire" wrapping: `{"<ndjson_blob>": {}}` (detected by newline-in-key + empty-value heuristic)

Response (`HealthIngestResponse`):
```
{
  "received": 24,
  "inserted": 20,
  "updated":  4,
  "rejected": [{"index": 7, "reason": "out_of_range:above_max"}]
}
```

### User endpoints (session-auth)

- `GET    /api/v1/health-metrics?kind=&from_ts=&to_ts=&limit=&offset=` — raw rows
- `GET    /api/v1/health-metrics/aggregate?period=hour|day|week|month|year&from_ts=&to_ts=`
- `DELETE /api/v1/health-metrics?kind=heart_rate|steps` — **DELETE ROWS of that kind** (no NULL-ing)
- `DELETE /api/v1/health-metrics/all` — DELETE every row
- `GET    /api/v1/health-metrics/tokens`
- `POST   /api/v1/health-metrics/tokens`
- `DELETE /api/v1/health-metrics/tokens/{id}`

## Config reference (`src/core/config/health_metrics.py`)

| Setting                                       | Default | Description                                                   |
| --------------------------------------------- | ------- | ------------------------------------------------------------- |
| `health_metrics_enabled`                      | `false` | Master feature flag                                           |
| `health_metrics_rate_limit_per_hour`          | `60`    | Sliding-window max req / hour / token                         |
| `health_metrics_max_samples_per_request`      | `1000`  | Batch size guard (`413` if exceeded)                          |
| `health_metrics_heart_rate_min`               | `20`    | Below → sample rejected                                       |
| `health_metrics_heart_rate_max`               | `250`   | Above → sample rejected                                       |
| `health_metrics_steps_min`                    | `0`     | Below → sample rejected                                       |
| `health_metrics_steps_max`                    | `15000` | Above → sample rejected (per-sample bound, not daily total)   |

## Upsert semantics (PostgreSQL)

`repository.upsert_samples()` uses `INSERT ... ON CONFLICT (user_id, kind, date_start, date_end) DO UPDATE` with the PostgreSQL-specific `RETURNING (xmax = 0) AS inserted` trick to discriminate new rows from updated rows in a single round-trip:

- `xmax = 0` → no prior tuple version → insert
- `xmax != 0` → an existing row was updated → update

This yields both counters (`inserted`, `updated`) without a separate `SELECT`. Re-sending the same sample for the same `(user_id, kind, date_start, date_end)` overwrites `value` and `source`, refreshes `updated_at`, and counts as an update.

**Intra-batch dedupe with per-kind arbitrage** — Before the UPSERT, `_merge_duplicate_samples` collapses samples sharing the same `(date_start, date_end)` tuple. Without this, PostgreSQL raises `CardinalityViolationError` ("ON CONFLICT DO UPDATE command cannot affect row a second time"). This is a real case in practice: iOS Shortcuts emits overlapping samples when the Apple Watch and iPhone both report measurements on the same interval. Merge strategy is per-kind:

| Kind | Strategy | Rationale |
| ---- | -------- | --------- |
| `steps` | **MAX** | Watch (worn) and iPhone (carried) count complementary subsets of movement; neither is a superset of the other, so MAX approximates ground truth better than SUM (double-count) or AVG (under-count). |
| `heart_rate` | **AVG** (rounded to int) | Both sensors target the same physiological signal; arithmetic mean is the most honest fusion. Uses Python's banker's rounding at `.5`. |
| (other) | last-wins | Forward-compat fallback; service-layer validation already rejects unknown kinds upstream. |

Collapsed duplicates are reported as `updated` in the response, emit a `health_batch_duplicates_collapsed` warning log (with `user_id`, `kind`, `duplicates`, `received`), and increment `health_samples_batch_duplicates_total{kind}`.

## Mixed per-sample validation

`service._validate_sample(raw, kind)` returns a `_SampleValidation` dataclass:

- `valid: bool`
- `payload: dict | None` — normalized `date_start`, `date_end`, `value`, `source` (only on success)
- `reason: str | None` — one of `out_of_range`, `malformed`, `missing_field`, `invalid_date` (prefixed label: `out_of_range:below_min`, etc.)

Failed samples are collected in the `rejected` list with their **0-based index** in the original batch. Valid samples in the same batch are persisted regardless — one bad sample does not fail the whole request.

## Datetime normalization

`service._normalize_datetime()` accepts:
- ISO 8601 strings with any timezone (`"2026-04-21T14:30:00+02:00"`, `"2026-04-21T12:30:00Z"`)
- Existing aware `datetime` objects

It rejects naive (tz-less) datetimes, converts to UTC, and truncates microseconds. The UTC+second floor is what makes the uniqueness constraint stable across TZ offsets and clock precisions.

## Aggregation

`aggregator.aggregate_samples()` takes the ascending-ordered list of samples in the window and emits one `HealthMetricAggregatePoint` per bucket slot — empty slots carry `has_data=False` so the frontend can render gaps without client-side gap detection.

Per-bucket fields:
- `heart_rate_avg / min / max` — over the bucket's `kind="heart_rate"` samples (`None` if the bucket has no HR sample).
- `steps_total` — sum of values over the bucket's `kind="steps"` samples (`None` if the bucket has no steps sample).
- `has_data` — `False` if the bucket has no sample of any kind.

Period-wide averages:
- `heart_rate_avg` = arithmetic mean of every HR sample in the window.
- `steps_per_day_avg` = `total_steps / total_days` (`None` when zero steps).

## Observability

### Prometheus metrics (`src/infrastructure/observability/metrics_health_metrics.py`)

| Metric                                             | Type      | Labels                      |
| -------------------------------------------------- | --------- | --------------------------- |
| `health_samples_upserted_total`                    | Counter   | `kind`, `operation`         |
| `health_metrics_ingest_duration_seconds`           | Histogram | —                           |
| `health_metrics_validation_rejected_total`         | Counter   | `field`, `reason`           |
| `health_metrics_rate_limit_hits_total`             | Counter   | —                           |
| `health_metrics_auth_failures_total`               | Counter   | `reason`                    |
| `health_metrics_tokens_generated_total`            | Counter   | —                           |
| `health_metrics_tokens_revoked_total`              | Counter   | —                           |
| `health_metrics_deleted_total`                     | Counter   | `scope`                     |

`operation` values: `insert | update`. `kind` values: `heart_rate | steps`. All label cardinalities are bounded on purpose (the `source` slug is never promoted to a metric label).

Active-token count is computable as
`sum(health_metrics_tokens_generated_total) - sum(health_metrics_tokens_revoked_total)` — no dedicated gauge, to keep the cardinality and scheduler surface small.

### Structured log events

`health_samples_ingested`, `health_sample_rejected`, `health_samples_deleted`, `health_metric_token_generated`, `health_metric_token_revoked`, `health_metric_token_rejected`, `health_metric_rate_limit_hit`, `health_metric_parser_error`.

Logs carry `user_id`, `kind`, `source`, counts, and validation metadata — never raw per-sample values.

### Grafana

`infrastructure/observability/grafana/dashboards/21-health-metrics.json` — panels cover upsert rate by kind/operation, latency percentiles, validation rejections per field/reason, auth/rate-limit failures, token lifecycle, and deletions by scope.

## Frontend

- Hook: [apps/web/src/hooks/useHealthMetrics.ts](../../apps/web/src/hooks/useHealthMetrics.ts)
- Settings section: [apps/web/src/components/settings/HealthMetricsSettings.tsx](../../apps/web/src/components/settings/HealthMetricsSettings.tsx)
- Charts: [apps/web/src/components/health_metrics/HealthMetricsCharts.tsx](../../apps/web/src/components/health_metrics/HealthMetricsCharts.tsx)
- i18n namespace: `healthMetrics.*` in all 6 locale files (`en/fr/de/es/it/zh`).

## Extending the kind taxonomy

Adding a new kind (e.g. `spo2`):

1. `constants.py` — add `HEALTH_METRICS_KIND_SPO2` and append to `HEALTH_METRICS_KINDS`.
2. `config/health_metrics.py` — add bound settings + `.env.example`.
3. Alembic migration — update the `ck_health_samples_kind` check constraint.
4. `service._validate_sample()` — add a branch computing `(lo, hi)` for the new kind.
5. `aggregator.aggregate_samples()` — add aggregation logic for the new kind (simple addition or bucket-reduced stats).
6. `schemas.HealthMetricAggregatePoint` — add the new aggregate field(s).
7. Frontend — extend `HealthMetricsAggregatePoint` + charts + i18n keys (6 languages).
8. Tests — mirror the existing per-kind validation and aggregator tests.

The key insight: the polymorphic single-table design means extending the taxonomy never requires new tables or new endpoints — only a new `kind` discriminator value and its validation/aggregation branches.
