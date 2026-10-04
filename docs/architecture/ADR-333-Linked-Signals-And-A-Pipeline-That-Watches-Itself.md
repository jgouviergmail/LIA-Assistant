# ADR-333 — The four signals link to each other, and the pipeline watches itself

**Status:** Accepted — 2026-10-03 (production observability audit after v2.4.0; owner
choices on the dashboards' default range and on their links).

**Amends:** ADR-148 (a metric nobody can see — extended to the observability pipeline's
own series), ADR-317 (log content redaction now runs on every container's line under
one label set).

**Reference:** [docs/technical/GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md),
[docs/technical/ALERTING.md](../technical/ALERTING.md),
[docs/guides/GUIDE_OBSERVABILITY.md](../guides/GUIDE_OBSERVABILITY.md).

## Context

Every finding was measured in production before it was touched:

1. **The links between signals pointed at nothing.** The logs→trace derived field
   matched `trace_id=` while the API writes JSON (0 of 200 real lines matched); the
   trace→metrics link lost its `$__tags` in provisioning; Prometheus received 19,045
   exemplars a day and stored none (no exemplar storage).
2. **One label lied.** Alloy set `job="api"` on every container's line, so a query for
   the API's logs also read Tempo, Redis, Grafana and PostgreSQL.
3. **The pipeline was blind to itself.** Loki, Alloy, Tempo and Grafana were not
   scraped: lines dropped or refused on the way to Loki left no signal.
4. **Noise hid signal.** Grafana traced itself (59 % of Tempo's spans), the API emitted
   one span per ASGI message (88 % of its spans), Tempo failed 30 polls a day on a
   retention/poller race, and dashboards opened on ranges chosen one by one.

## Decision

1. **Every signal opens the next.** A log line opens its trace (derived field on the
   JSON `trace_id`), a trace opens its logs (`{service="api"} |= <trace id>`) and its
   metrics (span metrics, `$__tags` restored), a latency point opens its trace
   (Prometheus exemplar storage, labelled `traceID` as the datasource names it). The
   Prometheus datasource declares the real scrape interval (30 s).
2. **A label says what it is.** `job` names the compose service; the content
   redaction runs under `{project="lia"}` on every container, debug lines excepted.
3. **The pipeline watches itself, cheaply.** Loki, Alloy, Tempo and Grafana are
   scraped for `up` plus a declared keep-list each (about twenty series, not nine
   thousand); `ObservabilityScrapeTargetMissing` covers them; `LogsNotDelivered` fires
   on lines dropped or refused, with its recipe, catalogue query, runbook and
   promtool tests; dashboard 16 draws the pipeline. `test_pipeline_keep_lists_guard`
   holds every series a panel reads to its keep-list.
4. **The dashboards follow one convention** (owner choice, held by
   `test_grafana_dashboard_conventions_guard`): every dashboard opens on 7 days and
   refreshes every 5 minutes, logs and traces (06) on 4 hours; one shared « LIA
   dashboards » menu links all of them (tag `lia`), each opening on its own range.
5. **A series that can fire exists from the start.** Counters a dashboard or an alert
   reads by label are exported at zero from import (the push wake outcomes), so a
   pending alert means something happened, not that nothing was ever counted.

## Consequences

- Resource ceilings follow measurements (Prometheus 768 MB after a 504/512 MB peak,
  Loki 384 MB with a 64 MB results cache).
- Grafana reads Alertmanager's alerts and silences; its provisioning directories hold
  real files, so a restart logs no provisioning error.
- Found on the way and fixed under the same rules: a sentence with nothing to
  pronounce is no longer sent to the TTS engine (billed, then refused) and a TTS
  failure is logged by its code (ADR-303); a Google SKU priced at zero is free, not
  missing; the migrations configure logging before importing the models.
- What it does not do: it adds no tracing of the browser and keeps logs and traces
  on their existing retention (7 days in production).
