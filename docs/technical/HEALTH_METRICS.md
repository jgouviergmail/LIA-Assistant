# Health Metrics — technical reference

Domain: `src/domains/health_metrics/`
Feature flag: `HEALTH_METRICS_ENABLED` (default `false`)
ADR: [ADR-076](../architecture/ADR-076-Health-Metrics-Ingestion.md)
User guide: [GUIDE_IPHONE_SHORTCUTS_HEALTH](../guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md)

## Purpose

Ingest hourly health metrics from an iPhone Shortcut automation (heart rate, per-period step count, extensible payload), persist them per-user with server-side timestamps, and visualize them in the Settings UI at five period granularities.

## Architecture at a glance

```
iPhone Shortcut
    │   POST /api/v1/ingest/health  (Bearer hm_xxx)
    ▼
ingest_router.py  ───────▶  auth + rate limit (Redis)
    │
    ▼
service.ingest()  ───────▶  mixed per-field validation
    │
    ├─▶  health_metrics row (server timestamp)
    └─▶  last_used_at UPDATE on the token

Settings UI
    │   GET /api/v1/health-metrics/aggregate?period=…
    ▼
router.py  ─────────────▶  service.aggregate()
                                │
                                ▼
                          aggregator.py  (bucket + per-period sum)
```

## Database schema

### `health_metrics`

| Column             | Type          | Nullable | Notes                                              |
| ------------------ | ------------- | -------- | -------------------------------------------------- |
| `id`               | UUID PK       | No       | Generated                                          |
| `user_id`          | UUID FK       | No       | `users.id`, `ON DELETE CASCADE`                    |
| `recorded_at`      | TIMESTAMPTZ   | No       | Server-side reception time (UTC)                   |
| `heart_rate`       | SMALLINT      | Yes      | bpm; NULL when out of `[20, 250]` or absent        |
| `steps`            | INTEGER       | Yes      | Steps over the inter-sample period; NULL when invalid/absent |
| `source`           | VARCHAR(32)   | No       | Slugified origin label; default `'unknown'`        |
| `created_at`       | TIMESTAMPTZ   | No       | From `TimestampMixin`                              |
| `updated_at`       | TIMESTAMPTZ   | No       | From `TimestampMixin`                              |

Index: `ix_health_metrics_user_recorded (user_id, recorded_at)`.

### `health_metric_tokens`

| Column          | Type          | Notes                                              |
| --------------- | ------------- | -------------------------------------------------- |
| `id`            | UUID PK       |                                                    |
| `user_id`       | UUID FK       | `ON DELETE CASCADE`                                |
| `token_hash`    | VARCHAR(64)   | SHA-256 hex digest (unique)                        |
| `token_prefix`  | VARCHAR(16)   | `hm_` + first 8 chars, displayed in UI             |
| `label`         | VARCHAR(64)   | User-supplied label                                |
| `last_used_at`  | TIMESTAMPTZ   | Updated on each successful ingestion               |
| `revoked_at`    | TIMESTAMPTZ   | When non-null, the token is invalidated            |
| `created_at`    | TIMESTAMPTZ   |                                                    |
| `updated_at`    | TIMESTAMPTZ   |                                                    |

The **raw token value is never stored**. It is generated via `secrets.token_urlsafe(24)` prefixed with `hm_`, shown to the user once in the `POST /tokens` response, and from then on exists only as a SHA-256 hash.

## API surface

### Ingestion (token-auth)

- `POST /api/v1/ingest/health` — Bearer `hm_xxx` header. Body `{"data": {"c": int, "p": int, "o": str?}}`. Returns 202 with `{status, recorded_at, stored_fields, nullified_fields}`.

### User endpoints (session-auth)

- `GET    /api/v1/health-metrics?from_ts=&to_ts=&limit=&offset=` — raw rows
- `GET    /api/v1/health-metrics/aggregate?period=hour|day|week|month|year&from_ts=&to_ts=` — bucketed points + period averages
- `DELETE /api/v1/health-metrics?field=heart_rate|steps` — UPDATE field=NULL
- `DELETE /api/v1/health-metrics/all` — DELETE rows
- `GET    /api/v1/health-metrics/tokens` — list
- `POST   /api/v1/health-metrics/tokens` — create (raw token returned once)
- `DELETE /api/v1/health-metrics/tokens/{id}` — revoke

## Config reference (`src/core/config/health_metrics.py`)

| Setting                                | Default | Description                                           |
| -------------------------------------- | ------- | ----------------------------------------------------- |
| `health_metrics_enabled`               | `false` | Master feature flag                                   |
| `health_metrics_rate_limit_per_hour`   | `5`     | Sliding-window max req / hour / token                 |
| `health_metrics_heart_rate_min`        | `20`    | Below → stored NULL + warn log                        |
| `health_metrics_heart_rate_max`        | `250`   | Above → stored NULL + warn log                        |
| `health_metrics_steps_min`             | `0`     | Below → stored NULL + warn log                        |
| `health_metrics_steps_max`             | `15000` | Above → stored NULL + warn log (per-sample, NOT daily) |

## Aggregation

`aggregator.aggregate_metrics()` takes the ascending-ordered list of rows in the requested window and emits one `HealthMetricAggregatePoint` per bucket slot (every slot — empty slots carry `has_data=False`). Each sample's `steps` field is already the count for the inter-sample period, so bucket aggregation is a simple `SUM`.

Per-bucket fields:
- `heart_rate_avg / min / max` — over the bucket's HR samples (None if no HR sample carried a value).
- `steps_total` — sum of every non-null `steps` in the bucket (None if every sample's `steps` is NULL).
- `has_data` — False if the bucket has no sample at all.

Period-wide averages:
- `heart_rate_avg` = arithmetic mean of every non-null `heart_rate` sample.
- `steps_per_day_avg` = `total_steps / total_days_in_window` (None if zero steps).

## Mixed per-field validation

`service._validate_heart_rate()` and `_validate_steps()` each return a `_FieldOutcome` with three flags:
- `stored_value` — what to persist (int or None)
- `was_stored` — payload carried a valid value
- `was_nullified` — payload carried a value that failed bounds

A row is always created on a successful POST. At least one of its columns may be NULL. The response `status` is `"accepted"` when no field was nullified, `"partial"` otherwise.

## Observability

### Prometheus metrics (`src/infrastructure/observability/metrics_health_metrics.py`)

| Metric                                             | Type      | Labels                      |
| -------------------------------------------------- | --------- | --------------------------- |
| `health_metrics_ingested_total`                    | Counter   | `status`                    |
| `health_metrics_ingest_duration_seconds`           | Histogram | —                           |
| `health_metrics_validation_rejected_total`         | Counter   | `field`, `reason`           |
| `health_metrics_rate_limit_hits_total`             | Counter   | —                           |
| `health_metrics_auth_failures_total`               | Counter   | `reason`                    |
| `health_metrics_tokens_generated_total`            | Counter   | —                           |
| `health_metrics_tokens_revoked_total`              | Counter   | —                           |
| `health_metrics_deleted_total`                     | Counter   | `scope`                     |

Active-token count is computable as
`sum(health_metrics_tokens_generated_total) - sum(health_metrics_tokens_revoked_total)` — no dedicated gauge, to keep the cardinality and scheduler surface small.

### Structured log events

`health_metric_ingested`, `health_metric_rejected`, `health_metric_field_invalid`, `health_metric_deleted`, `health_metric_token_generated`, `health_metric_token_revoked`, `health_metric_token_rejected`, `health_metric_rate_limit_hit`.

Logs never carry raw metric values — only `user_id`, `source`, `status`, and validation metadata.

### Grafana

`infrastructure/observability/grafana/dashboards/21-health-metrics.json` — panels cover ingestion rate by status, latency percentiles, validation rejections per field/reason, auth/rate-limit failures, token lifecycle, and deletions by scope.

## Frontend

- Hook: [apps/web/src/hooks/useHealthMetrics.ts](../../apps/web/src/hooks/useHealthMetrics.ts)
- Settings section: [apps/web/src/components/settings/HealthMetricsSettings.tsx](../../apps/web/src/components/settings/HealthMetricsSettings.tsx)
- Charts: [apps/web/src/components/health_metrics/HealthMetricsCharts.tsx](../../apps/web/src/components/health_metrics/HealthMetricsCharts.tsx)
- i18n namespace: `healthMetrics.*` in all 6 locale files (`en/fr/de/es/it/zh`).

## Extending the payload

Adding a new metric (e.g. `spo2`):

1. `constants.py` — add `HEALTH_METRICS_FIELD_SPO2`, bounds, append to `HEALTH_METRICS_DELETABLE_FIELDS`.
2. `config/health_metrics.py` — add bound settings + `.env.example`.
3. Alembic migration — `ADD COLUMN spo2 SMALLINT NULL`.
4. `models.py` — add `spo2: Mapped[int | None]`.
5. `schemas.HealthMetricPayload` — add `s: int | None`.
6. `service._validate_spo2()` — mirror the two existing validators.
7. `service.ingest()` — call the new validator and include the field in stored/nullified lists.
8. `aggregator` — optional, depending on the chart shape you want.
9. Frontend — extend `HealthMetricsAggregatePoint` + charts + i18n keys.
10. Tests — mirror the existing per-field validation test.
