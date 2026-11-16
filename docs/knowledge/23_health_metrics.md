# Health data

## What is the “Health data” section?

A dedicated ingestion API that accepts heart-rate and step measurements from **any source**: iPhone Shortcuts automation (the documented primary use case), Android scripts, third-party integrations, or compatible IoT devices. Ingestion works in **batches** (up to 1000 samples per request), each measurement carrying its own `date_start` / `date_end` interval. Your data is visualized in **Settings → Features → Health data** as a line chart (HR) and bar chart (steps), with a period selector (hour / day / week / month / year), a dashed line for the period average, and the actual aggregation window displayed in the statistics.

## How do I set up my iPhone to push data?

**1. Generate a token** from **Settings → Features → Health data → Ingestion API**. The token starts with `hm_` and is shown *once* only — copy it immediately. The same token authenticates both endpoints (steps + heart rate).
**2. Create two iOS Shortcuts** (one per kind) that fetch the day's Apple Health samples and send them in the format below.
**3. Schedule an automation** — on iPhone unlock or at a fixed time — that runs both Shortcuts. Re-sending the same day is free: the server deduplicates automatically.

**📤 The request:**
• `POST https://your-lia-domain/api/v1/ingest/health/steps` for steps, `POST https://your-lia-domain/api/v1/ingest/health/heart_rate` for heart rate
• headers: `Authorization: Bearer hm_…` and `Content-Type: application/json`
• body: a JSON array of samples, up to 1,000 per request; `{"data": [...]}`, a single sample or one JSON sample per line (NDJSON) are accepted too

**📋 Each sample:**
• `date_start` and `date_end` (required): start and end of the measured interval, as ISO 8601 text **with a timezone** — for example `2026-04-21T06:00:00+02:00`, or the `Z` suffix for UTC; a date without a timezone is rejected
• `steps` for steps, `heart_rate` for heart rate in bpm (required): an integer
• `o` (optional): where the sample comes from, for example `iphone`

**💡 Example (steps):**
`[{"date_start": "2026-04-21T06:00:00+02:00", "date_end": "2026-04-21T07:00:00+02:00", "steps": 1234, "o": "iphone"}]`
For heart rate, replace `steps` with `heart_rate`.

**✅ The response:**
`{"received": 1, "inserted": 1, "updated": 0, "rejected": []}`: every rejected sample is listed in `rejected` with its index and reason, the others are stored. An unreadable body returns `400`, an invalid token `401`, an oversized batch `413` and too frequent sends `429`.

👉 Step-by-step guide: `docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md`.

## What data is sent and stored?

Each request is an **array of self-timestamped samples**, in the format detailed in “How do I set up my iPhone to push data?”:
• for steps: `{date_start, date_end, steps, o}` — the measurement interval and the step count over it
• for heart rate: `{date_start, date_end, heart_rate, o}` — the interval and the bpm value

The server UTC-normalizes dates and applies **per-sample physiological validation**: HR outside [20, 250] bpm or steps outside [0, 15,000] are individually rejected with their index and a bounded reason (valid siblings in the same batch persist). When Apple Watch and iPhone measure the same period, LIA merges them intelligently: **MAX** for steps, **rounded average** for heart rate. No raw values are ever logged by the server.

## How do I delete my health data?

In **Settings → Features → Health data → Data management** three actions are available:

- **Delete heart rates**: deletes every heart-rate measurement (steps preserved).
- **Delete steps**: deletes every step measurement (HR preserved).
- **Delete**: erases every measurement permanently (your ingestion tokens remain active).

If you delete your LIA account, all health data is wiped automatically (SQL cascade).

## Is my token safe if intercepted?

No: anyone who obtains the token can send health samples into your account until you revoke it. The token only permits health-data ingestion; it cannot read your account or perform other actions.

Generate and revoke tokens in **Settings → Health data → Ingestion API**. The full token is shown only once; afterwards only its identifying prefix remains visible. The server stores its hash, not the token itself. You can issue separate tokens for your devices and revoke each independently.

If a token is exposed, revoke it and replace it in your automation. Keeping a hash on the server does not protect a token copied elsewhere.

## How do I ask LIA about my health data?

Enable the **Settings → Health data → Assistant** toggle (off by default, *opt-in*). While off, no health data ever reaches the LLM. Once on, you can:

- **Ask factual questions in chat**: “How many steps today?”, “My heart rate this week?”, “Steps day by day over the last 7 days?”, “Am I walking less than usual?”, “Anything unusual in my health lately?”. LIA answers with factual figures (totals, averages, deltas vs baseline) — never medical diagnosis.
- **Receive proactive notifications** that combine health + weather + calendar (“Sunny today and 4 days of inactivity → short walk?”).
- **Enrich your memories and internal journals** with biometric context at capture time (only deltas and trends — never raw values).

A single switch governs these 4 integrations. The 28-day rolling baseline qualifies comparisons honestly (“based on only N days of data” while history is under 7 days).

## Why do my health charts show gaps, and why don't the statistics change with the period?

The charts draw **one slot per unit** of the period you pick: hourly over the last day, daily over the last week, weekly over about three months, monthly over the last year, yearly over five years. A slot with no measurement stays **empty** — a gap, never a line invented between two points.
• **Heart rate**: a line of the average in each slot
• **Steps**: a bar with the total of each slot
• a dashed line marks the average over the period

The **Statistics** — average, minimum and maximum heart rate, average steps per day, total steps — summarise the range written under them as the **Aggregation window**. If all your measurements fit in the shortest range, the figures stay the same whatever the period: nothing is wrong, there is simply no older data. With nothing to show, the chart says **No data for this period**.

## Are my steps counted twice if I wear an Apple Watch?

No. The Shortcut sends the samples of all your devices: the iPhone in your pocket and the Apple Watch on your wrist count the same walk, over intervals that overlap. LIA counts each slice of time once, at the highest rate a device measured — the history already received included. There is nothing to set.

Days are yours: today, the daily bars, the averages and the comparisons start at midnight in your account’s timezone. A small gap with the Health app remains possible: the steps taken since the Shortcut’s last send are not in LIA yet, and Health keeps one device per period by its source priority.

## Further reading

- [Health data technical reference](../technical/HEALTH_METRICS.md)
- [iPhone Shortcuts setup guide](../guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md)
