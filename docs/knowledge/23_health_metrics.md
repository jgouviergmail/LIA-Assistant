# Health Metrics — iPhone Shortcuts ingestion

## What are Health Metrics?

A new feature (v1.17.0) that lets your iPhone automatically push your Apple Health measurements (heart rate, step count) to LIA via a Shortcuts automation, then visualizes them in a dedicated Settings section.

**Design principle**: LIA acts as the storage and visualization layer; the iPhone Shortcut is the producer. The endpoint is authenticated by a per-user token (never a session cookie) so a Shortcut can run unattended.

## What gets sent

Every hour (or any frequency you configure), the Shortcut sends a minimal JSON payload:

```json
{ "data": { "c": 72, "p": 4521, "o": "iphone" } }
```

- `c` — last heart rate sample (bpm)
- `p` — number of steps recorded since the previous sample (NOT a daily cumulative)
- `o` — origin label (free text, slugified server-side; defaults to `unknown`)

The server timestamps each sample at reception (UTC). The client never supplies a timestamp.

## Where to find it

**Settings → Features → Health data**. Four sub-sections behind one collapsible card:

1. **Ingestion API** — full URL to copy into your iPhone Shortcut, list of your tokens, button to generate a new one or revoke an existing one.
2. **Charts** — heart-rate line chart + steps bar chart. A period selector at the top (hour / day / week / month / year) drives both. A dashed reference line shows the period average.
3. **Statistics** — period-wide aggregates: HR avg / min / max, average steps per day, total steps over the period.
4. **Data management** — three deletion buttons: delete all heart rates, delete all steps, or wipe everything. Tokens are not affected by data deletion.

## Token security

- The raw token is shown **only once** at generation time. Copy it immediately. After that, only an 8-character display prefix (`hm_xxxxxxxx…`) remains visible.
- The server stores a SHA-256 hash. Nobody (not even an admin) can recover the raw value after creation.
- A token only authorizes the ingestion endpoint. It cannot read your account or perform any other action.
- You can hold multiple tokens at once (one per device, for example). Each one is revocable independently from the UI.
- Rate limit: 5 requests per hour per token (Redis sliding window) to block spam.

## Validation

Each field is validated independently against physiological bounds (configurable in `.env`):

| Field | Default range | Out-of-range behavior |
| ----- | ------------- | --------------------- |
| `c` (heart rate) | [20, 250] bpm | stored as NULL + warning log |
| `p` (steps) | [0, 15 000] per sample | stored as NULL + warning log |

Crucially, **mixed-validation** is applied per field: a payload like `{"c": 0, "p": 4521}` results in a row with `heart_rate=NULL` AND `steps=4521` — the valid sibling field is preserved instead of dropping the whole row.

The raw values are never written to logs (GDPR-aware): only `direction=below_min` or `above_max` is captured for observability.

## Charts

The aggregator emits one bucket per slot in the requested window — even slots with no sample (`has_data=False`). The frontend uses `recharts` with `connectNulls={false}` so missing data shows as a gap rather than an interpolated line.

- **Heart rate**: line chart with average / min / max per bucket. Dashed line at period average.
- **Steps**: bar chart, simple SUM per bucket (each sample is already a per-period increment). Dashed line at average steps per day over the requested window.

## How to set up the iPhone Shortcut

The end-to-end procedure (steps A-E + hourly automation) is documented in [`docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md`](../guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md). High-level summary:

1. Generate a token in Settings (copy it once).
2. Create a Shortcut that fetches the latest heart rate sample and the steps recorded over the last hour.
3. POST the JSON to `/api/v1/ingest/health` with `Authorization: Bearer hm_xxx`.
4. Schedule the Shortcut hourly via Shortcuts → Automation.

## Privacy by design

- Health data is GDPR special-category (article 9). LIA stores only what the iPhone sends and never logs raw values.
- Encryption at rest is handled by PostgreSQL standard volume encryption.
- Right to erasure: per-field delete + full delete from the UI. Account deletion cascades to all rows automatically.
- No data is shared with third parties — everything stays in the LIA database.

## Known limitations

- One sample per hour is a coarse signal for heart rate. The "period average" is the average of instantaneous samples, not a true physiological average. Higher push frequency would improve precision.
- iPhone Shortcuts cannot batch-replay missed hours: if the device is offline at trigger time, that hour simply has no data point (the chart shows a gap).
- The chart `Hour` view defaults to the last 24 hours; coarser views default to: 7 days (Day), 12 weeks (Week), 365 days (Month), 5 years (Year).

## Related references

- ADR-076 — Health Metrics Ingestion via Per-User Tokens
- `docs/technical/HEALTH_METRICS.md` — full technical documentation
- `docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md` — step-by-step iPhone setup guide
- Settings page: `apps/web/src/components/settings/HealthMetricsSettings.tsx`
- Backend domain: `apps/api/src/domains/health_metrics/`
