# Health Metrics — ingestion + assistant integrations

## What are Health Metrics?

A feature that lets you push heart-rate and step-count measurements to LIA from any source — the documented, simplest path is an iPhone Shortcuts automation pushing Apple Health, but any system that can issue a signed HTTP call (Android automation, personal script, compatible IoT) can feed the ingestion API. A unified per-user toggle exposes those measurements to the assistant's three central loops — conversation, proactivity, and introspection.

**Design principle**: LIA acts as the storage and visualization layer; the producer is whatever you wire in. The endpoints are authenticated by a per-user token (never a session cookie) so automations can run unattended. Ingestion is **batch-based** rather than continuous push — each sample carries its own `date_start` / `date_end`, and the Shortcut (or equivalent) ships the day's samples in one payload whenever it fires (on unlock or at a fixed time).

## What gets sent

Each request is an **array of self-timestamped samples**. One endpoint per measurement kind:

```
POST /api/v1/ingest/health/steps
[
  {"date_start": "2026-04-21T06:00:00+02:00",
   "date_end":   "2026-04-21T07:00:00+02:00",
   "steps": 1234, "o": "iphone"},
  ...
]
```

```
POST /api/v1/ingest/health/heart_rate
[
  {"date_start": "2026-04-21T06:15:00+02:00",
   "date_end":   "2026-04-21T06:15:30+02:00",
   "heart_rate": 72, "o": "iphone"},
  ...
]
```

- `date_start` / `date_end` — ISO 8601 with timezone offset; the server UTC-normalizes and truncates to the second (idempotency key).
- `steps` / `heart_rate` — the scalar value for the interval (integer).
- `o` — origin label (free text, slugified server-side; defaults to `iphone`).

The parser accepts four envelope shapes to absorb iOS Shortcut authoring variations: canonical JSON array, NDJSON, `{"data": [...]}`, and the "Dictionary" wrapping where the NDJSON is encoded as the sole key of an outer dict with an empty value.

## Where to find it

**Settings → Features → Health data**. Five sub-sections behind one collapsible card:

1. **Ingestion API** — two URLs (steps + heart_rate) to paste into your iPhone Shortcuts, list of your tokens, button to generate a new one or revoke an existing one.
2. **Assistant** — a single toggle that opts your health data into the assistant's agents, proactive notifications, memory extractor, and journal consolidation. **Default: off**. No health data ever reaches the LLM when this is off.
3. **Charts** — heart-rate line chart + steps bar chart. A period selector at the top (hour / day / week / month / year) drives both. A dashed reference line shows the period average.
4. **Statistics** — period-wide aggregates: HR avg / min / max, average steps per day, total steps over the period. The actual aggregation window (from/to) is displayed so you can tell which data is being summarized.
5. **Data management** — three deletion buttons: delete all heart rates, delete all steps, or wipe everything. Tokens are not affected by data deletion.

## Token security

- The raw token is shown **only once** at generation time. Copy it immediately. After that, only an 8-character display prefix (`hm_xxxxxxxx…`) remains visible.
- The server stores a SHA-256 hash. Nobody (not even an admin) can recover the raw value after creation.
- A token only authorizes the ingestion endpoints. It cannot read your account or perform any other action.
- The same token works for both `/steps` and `/heart_rate`.
- You can hold multiple tokens at once (one per device, for example). Each one is revocable independently from the UI.
- Rate limit: **60 requests per hour per token** (Redis sliding window, configurable). Batch size cap: 1000 samples per request (HTTP 413 beyond).

## Validation and deduplication

### Per-sample validation (mixed)

Each sample is validated independently against physiological bounds (configurable in `.env`):

| Field | Default range | Out-of-range behavior |
| ----- | ------------- | --------------------- |
| `heart_rate` | [20, 250] bpm | individual sample rejected with `out_of_range:above_max` or `:below_min` |
| `steps` | [0, 15 000] per sample | same |

Other bounded rejection reasons: `malformed`, `missing_field`, `invalid_date`. The response lists `rejected[{index, reason}]` so the client knows exactly which samples were dropped and why. Valid siblings in the same batch persist — one bad sample never kills the day.

The raw values are never written to logs (GDPR-aware): only the reason label is captured for observability.

### Intra-batch dedupe (per-kind arbitrage)

iOS legitimately emits overlapping samples when the Apple Watch and iPhone both report the same interval. PostgreSQL's `ON CONFLICT DO UPDATE` refuses to touch the same target row twice per statement, so the server fuses intra-batch duplicates on `(date_start, date_end)` before the UPSERT:

- `steps` → **MAX** across the group (Watch and iPhone count complementary subsets of movement; MAX approximates ground truth better than SUM double-count or AVG under-count).
- `heart_rate` → **AVG** rounded to the nearest int (two sensors aim at the same physiological signal; averaging is the most honest fusion).

Collapsed duplicates are reported as `updated` in the response and tracked via the Prometheus counter `health_samples_batch_duplicates_total{kind}`.

### Idempotent upsert

The uniqueness key is `(user_id, kind, date_start, date_end)`. Re-sending the same sample overwrites `value` + `source` + `updated_at` — so the Shortcut can safely re-push the same day every unlock without creating duplicates.

## Charts

The aggregator emits one bucket per slot in the requested window — even slots with no sample (`has_data=False`). The frontend uses `recharts` with `connectNulls={false}` so missing data shows as a gap rather than an interpolated line.

- **Heart rate**: line chart with average / min / max per bucket. Dashed line at period average.
- **Steps**: bar chart, simple SUM per bucket. Dashed line at average steps per day over the requested window.
- **Statistics panel**: displays the actual aggregation window (e.g. "Apr 21 18:00 → Apr 22 18:00") so you can see which time range is being summarized. This defuses the "HR stats don't move when I change period" confusion — they're invariant when all your samples already fit inside the smallest window.
- **Tooltip contrast**: tooltips respect the active theme (light/dark) via shadcn CSS variables.

## How to set up the iPhone Shortcut

The end-to-end procedure is documented in [`docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md`](../guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md). High-level summary:

1. Generate a token in Settings (copy it once).
2. Create **two** Shortcuts: one that fetches the day's step samples from Apple Health and POSTs the JSON array to `/api/v1/ingest/health/steps`, and one that does the same for heart_rate and POSTs to `/api/v1/ingest/health/heart_rate`. Both use `Authorization: Bearer hm_xxx`.
3. Schedule via Shortcuts → Automation: run both on iPhone unlock or at a fixed time (or both). Re-sending the same day is free.

## Privacy by design

- Health data is GDPR special-category (article 9). LIA stores only what the iPhone sends and never logs raw values.
- Encryption at rest is handled by PostgreSQL standard volume encryption.
- Right to erasure: per-kind delete + full delete from the UI. Account deletion cascades to all rows automatically.
- No data is shared with third parties — everything stays in the LIA database.
- **Opt-in gated downstream**: the **Assistant** toggle defaults to *off*. Until enabled, the assistant's agents, Heartbeat, memory extractor, and journal consolidation never touch your health samples.
- **No raw values in downstream artifacts**: when assistant integrations are on, memories, journals, and Heartbeat signals carry **deltas / trends / events only** — never raw bpm / step counts. Raw integers remain in `health_samples` where GDPR erasure applies.

## What the assistant can do with your health data

When the **Assistant** toggle is on:

1. **Ask it questions in chat**. A single `health_agent` owns seven hand-crafted tools covering steps (summary / breakdown / baseline), heart rate (summary / baseline), and cross-kind overview + change-detection. Typical questions:
   - Steps — "How many steps today?", "Steps cette semaine ?", "Show my last 10 days", "Am I walking less than usual?"
   - Heart rate — "What's my avg heart rate this week?", "Is my HR higher than usual?"
   - Overview — "How's my health today?", "Anything unusual this week?"

   Responses are factual (numbers + trends). The assistant never diagnoses. Summary + overview tools take ISO 8601 `time_min` / `time_max` bounds (same pattern as `calendar_tools.search_events_tool`): LIA resolves temporal phrases like "this week" or "last month" into concrete date ranges before the planner runs, so the tool receives exact start/end dates. Defaults when omitted: today 00:00 UTC → now.
2. **Proactive notifications (Heartbeat)**. LIA injects a compact health signals block into its proactive-messaging context — baseline deltas, recent variations, inactivity streaks — so it can time a reminder when you've been inactive for 4 days, or frame a rebond combining weather + health.
3. **Memory introspection**. When LIA extracts a durable memory from a conversation with significant emotional charge, it may attach a compact `context_biometric` blob to the memory (baseline deltas at that moment). Future recalls carry the biometric frame as context — never the raw values.
4. **Journal consolidation**. LIA's internal operational journal can factor health signals into reflections ("the user has been less active this week — revisit my assumptions about their routine"). Never diagnostic.

**Adaptive baseline**. The first ~7 days of data use a `bootstrap` mode (median of all available days) — LIA always qualifies statements with "based on only N days of data". Past 7 days, it switches to a `rolling` 28-day median.

## Adding a new kind (developer reference)

Adding a new kind (e.g. `sleep_duration`, `spo2`, `calories_burned`) is a single-file edit in the central `HEALTH_KINDS` registry plus a per-kind tool pack. See `docs/technical/HEALTH_METRICS.md` for the checklist. The service, repository, aggregator, heartbeat, memory, and journal pipelines iterate the registry — no code change needed in those modules.

## Known limitations

- The polymorphic single-table storage supports scalar measurements only. A future `workout` kind carrying multiple scalars would need a different schema (JSON column or a second table).
- The iOS "Dictionary" wrapping detection is heuristic (single key with embedded newline + empty value). If Apple ever changes the shape, the parser needs an update. The NDJSON fallback catches most degenerate cases.
- The chart `Hour` view defaults to the last 24 hours; coarser views default to: 7 days (Day), 12 weeks (Week), 365 days (Month), 5 years (Year).

## Related references

- ADR-076 — Health Metrics Ingestion via Per-User Tokens (revised 2026-04-21 for the polymorphic batch refactor)
- `docs/technical/HEALTH_METRICS.md` — full technical documentation
- `docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md` — step-by-step iPhone setup guide
- Settings page: `apps/web/src/components/settings/HealthMetricsSettings.tsx`
- Backend domain: `apps/api/src/domains/health_metrics/`
