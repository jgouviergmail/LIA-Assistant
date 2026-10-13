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

## Amendment 2026-10-12 — the exporters keep only what is read

Decision 3 applied to the stack's own targets. Measured on production on
2026-10-12 (memory analysis of the host): cAdvisor published 7,137 series, of
which the dashboards and rules read eight families (`container_cpu_usage_seconds_total`,
`container_last_seen`, `container_memory_usage_bytes`, `container_memory_working_set_bytes`,
`container_network_receive_bytes_total`, `container_network_transmit_bytes_total`,
`container_spec_memory_limit_bytes`, `container_start_time_seconds`); postgres-exporter
published 3,590, one per table for every `pg_stat_user_tables` column, of which four were
read (`pg_up`, `pg_settings_max_connections`, `pg_stat_database_numbackends`,
`pg_stat_database_tup_fetched`). Every other series cost Prometheus head memory and
cAdvisor CPU for nobody.

- **A keep-list per exporter job** in `prometheus.yml`, held by
  `test_pipeline_keep_lists_guard`, which now recognises an exporter's series by the
  metric-name prefix it declares (`EXPORTER_FAMILIES`): a panel selects
  `container_memory_working_set_bytes{name="lia-api-prod"}` with no `job` label, so the
  pipeline rule's `job="…"` selector could not see it. The guard also reads the
  recording rules and the product alerts, not only the core alerts.
- **cAdvisor computes only what is read**: `--docker_only=true` (no panel reads a
  systemd cgroup), `--store_container_labels=false` (18 compose labels per series,
  none read), `--housekeeping_interval=30s` under the 60 s scrape, and the per-file-system,
  block-io, per-cpu, load and perf families disabled at the source — the same flags in
  `docker-compose.prod.yml` and `docker-compose.dev.yml`.
- Measured on the dev stack after the change: the cAdvisor scrape keeps 168 samples of
  1,033 scraped and the postgres-exporter scrape 30 of 4,050; every family a panel or a
  rule reads is still served; cAdvisor's own working set fell from 586 MB to 21 MB at
  restart. On production the two jobs' 10,727 series become about 650.
- What it does not do: it touches no LIA metric (every one of those has a reader by
  the ADR-148 ratchet) and no alert; a future panel on a dropped exporter family fails
  the build with the family named, which is the whole point of the guard.
