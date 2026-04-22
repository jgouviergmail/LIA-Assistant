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

## Assistant tool surface

A single `health_agent` owns seven hand-crafted tools under
`src/domains/agents/tools/health_tools.py` — one agent ↔ one domain
pattern (mirrors `email_agent`, `event_agent`, `weather_agent`…).
Manifests live in
`src/domains/agents/health/catalogue_manifests.py`.

| Tool                                 | Kind        | Params                    | Purpose                                   |
|--------------------------------------|-------------|---------------------------|-------------------------------------------|
| `get_steps_summary_tool`             | steps       | `time_min`, `time_max`    | Total steps over a time window            |
| `get_steps_daily_breakdown_tool`     | steps       | `days` (1-30)             | Per-day breakdown over N days             |
| `compare_steps_to_baseline_tool`     | steps       | `window_days` (1-14)      | Recent window vs 28-day baseline          |
| `get_heart_rate_summary_tool`        | heart_rate  | `time_min`, `time_max`    | Avg / min / max bpm over a time window    |
| `compare_heart_rate_to_baseline_tool`| heart_rate  | `window_days` (1-14)      | Recent window vs 28-day baseline          |
| `get_health_overview_tool`           | cross-kind  | `time_min`, `time_max`    | Per-kind summary over a time window       |
| `detect_health_changes_tool`         | cross-kind  | `window_days` (1-14)      | Directional streaks + structural events   |

### Time window pattern (`time_min` / `time_max`)

Summary + overview tools use ISO 8601 bounds exactly like
`calendar_tools.search_events_tool`. The **QueryAnalyzer** in
`query_analyzer_service.py` pre-resolves temporal expressions into
`resolved_references` (e.g. `{"this week": "2026-04-20 to 2026-04-26"}`)
which the planner injects in its prompt. The planner then splits the
two dates across the tool's two parameters. Defaults when omitted:

- `time_min` → today 00:00 UTC (service: `compute_kind_summary`).
- `time_max` → `datetime.now(UTC)`.

The tool-side helper `_parse_iso_ts(value, *, param)` accepts bare
dates (`"2026-04-20"` → midnight UTC), datetimes with Z suffix, and
datetimes with explicit offset. Malformed inputs → `None` + warning
log → service falls back to defaults.

### Message-embedded figures

All factual figures (totals, averages, per-day values) are inlined in
`UnifiedToolOutput.message` so the Response LLM surfaces them directly.
The `structured_data` payload remains the canonical source for the
frontend and for `data_for_filtering`, but the Response LLM never
reads it — it only sees the `message` text. Pattern borrowed from
`weather_tools.get_current_weather_tool`.

### Toggle gating

Every tool short-circuits through `_check_user_toggle_or_error` which
returns `UnifiedToolOutput.failure(error_code="PERMISSION_DENIED")`
when `User.health_metrics_agents_enabled` is false. The toggle is
exposed via `PATCH /api/v1/auth/me/health-metrics-agents-preference`
and governs four integrations at once (tools, Heartbeat source,
memory extractor, journal consolidation) — one interrupt for the
user.

## Extending the kind taxonomy

Adding a new kind (e.g. `spo2`, `sleep_duration`, `calories_burned`) is
a single-file edit in the central registry plus adding a handful of
hand-crafted tools — the service, repository, aggregator, heartbeat,
memory, and journal pipelines iterate `HEALTH_KINDS` and pick up the
new kind transparently.

1. **`src/domains/health_metrics/kinds.py`** — add a new
   `HealthKindSpec(...)` entry to `HEALTH_KINDS`. Pick the correct
   `MergeStrategy` (MAX / AVG_ROUNDED / MIN / SUM / LAST_WINS),
   `AggregationMethod` (SUM / AVG_MIN_MAX / LAST_VALUE), and
   `BaselineKind` (DAILY_SUM / DAILY_AVG / RESTING). Declare the
   `legacy_response_fields` tuple only if you need backward-compat on
   `HealthMetricAggregatePoint` (new kinds can rely on `metrics_by_kind`
   instead).
2. **Alembic migration** — update the `ck_health_samples_kind` CHECK
   constraint to allow the new value.
3. **`config/health_metrics.py` + `.env.example`** — add per-kind bound
   fields (`health_metrics_<kind>_min` / `_max`). `get_active_bounds(spec)`
   reads them automatically.
4. **Add tools to `health_tools.py`** — two or three new hand-crafted
   `@tool` functions (typically a summary tool using `time_min` /
   `time_max` and a baseline-compare tool using `window_days`). Reuse
   `_check_user_toggle_or_error`, `_parse_iso_ts`, and
   `_format_delta_pct`. Inline factual figures in the `message`.
5. **Register the manifests** — declare
   `<kind>_summary_catalogue_manifest` in
   `src/domains/agents/health/catalogue_manifests.py` with
   `parameters=[_TIME_MIN_PARAM, _TIME_MAX_PARAM]` for a summary tool
   (or `[_WINDOW_DAYS_PARAM]` for a baseline tool). Add the manifest
   to `HEALTH_TOOL_MANIFESTS` and the tool name to
   `HEALTH_AGENT_MANIFEST.tools`.
6. **Prompt update** — extend `health_agent_prompt.txt` `<Logic>` with
   selection rules for the new tools and a `<Strategies>` example.
7. **i18n** — add the kind's display name in the 6 locale files
   (`healthMetrics.kinds.<kind>`) and the tool i18n keys
   (`healthMetrics.tools.<tool_name>`).

The key insight: the polymorphic single-table design + central registry
+ single-agent pattern means extending the taxonomy never requires new
tables, new endpoints, nor a new agent — only a registry entry and a
few tool wrappers.
