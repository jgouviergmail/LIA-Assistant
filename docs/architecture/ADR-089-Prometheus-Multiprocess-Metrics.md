# ADR-089: Multi-Worker Prometheus Metrics — Multiprocess Aggregation + Per-Gauge Mode Classification

**Status**: ✅ IMPLEMENTED (2026-06-03)
**Author**: Claude Code (Opus 4.8)

## Context

LIA prod runs `uvicorn --workers 4` (4 isolated processes — same family of multi-worker
issue as [ADR-063](ADR-063-Cross-Worker-Cache-Invalidation.md)). Metrics were exposed via a
dedicated HTTP-only server (`prometheus_client.start_http_server`) on `prometheus_metrics_port`
(9091), started inside **every** worker's lifespan.

**Bugs observed in prod**:
- Only the first worker binds 9091; the other 3 raise `[Errno 98] Address already in use`
  (3 `prometheus_metrics_server_failed` warnings on every (re)deploy).
- The single bound worker serves **only its own** in-process registry → request-rate /
  latency / counter metrics were undercounted by ~4× (Grafana saw ~1 worker of 4). DB-backed
  lifetime gauges happened to look right only because every worker sets the same value.

The naive fix (`prometheus_client` multiprocess mode) has a sharp edge: in multiprocess mode
every `Gauge` **without** an explicit `multiprocess_mode` defaults to `'all'`, exposing one
series per PID — which would **break dashboards** (e.g. a `sum()` over a DB-backed lifetime
gauge that all 4 workers set to the same value becomes ×4).

## Decision

Enable `prometheus_client` **multiprocess mode** and classify **every** Gauge.

### 1. Aggregated serving (prod only)

- `docker-entrypoint.sh` sets `PROMETHEUS_MULTIPROC_DIR` **only when launched with `--workers`**
  (single-worker dev `--reload` is untouched). RAM-backed (`/dev/shm`, spares the Raspberry Pi
  SD card; overridable). Creation is **non-fatal** under `set -e`: if the dir can't be prepared,
  multiprocess is disabled and the app still starts in single-process mode.
- `main.py` builds a `CollectorRegistry` + `MultiProcessCollector` when the env is set; the
  worker that binds 9091 serves the **aggregate of all workers** (the others write their files
  and skip serving — their bind failure is now logged at `debug`, not `warning`).
- `multiprocess.mark_process_dead(pid)` is called on lifespan shutdown so a stopped/recycled
  worker leaves the `live*` gauges (verified: runs on `--limit-max-requests` recycle too).

Counters and Histograms aggregate automatically (sum). Gauges need an explicit mode:

### 2. Per-gauge `multiprocess_mode` classification (45 gauges)

| Mode | Count | When | Examples |
|------|------:|------|----------|
| `mostrecent` | 26 | Value is **global / DB- or config-derived** — every worker sets the *same* number (summing would ×N) | all `llm_*` lifetime/period/by-model/by-node, DAU/WAU, `db_connection_pool_size` (config), `channel_active_bindings`, `checkpoints_table_size_bytes`, journals, `registry_size` |
| `livesum` | 14 | **Per-worker local** resource whose fleet total = sum of live workers | `db_connection_pool_checkedout/overflow/waiting`, `http_requests_in_progress`, `rag_*`, `*_active_count`, `websocket_connections_active`, `browser_*` |
| `livemax` | 4 | Per-worker, surface worst/freshest across live workers | `circuit_breaker_state`, `circuit_breaker_open_duration_seconds`, `lifetime_metrics_update_duration_seconds`, `lifetime_metrics_last_update_timestamp` |
| `livemin` | 1 | "Healthy only if **every** live worker is" | `mcp_server_health` |

> Heuristic: value from a **shared backend** (DB/Redis/config) → `mostrecent`; **per-worker**
> resource → `livesum`. Classification was adversarially reviewed against every `.set()` site.

### 3. Instrumentation fixes shipped alongside (preserving Grafana query contracts)

- `mcp_server_health`: `livemax` → `livemin` (surfaces partial outages instead of hiding them).
- `lifetime_metrics_error_total`: `Gauge` (gauge-as-counter antipattern) → real `Counter`
  (auto-aggregates; exposed name unchanged).
- `channel_active_bindings`: per-worker startup priming + `.inc()/.dec()` (drifted in
  multiprocess) → refreshed from the DB inside the lifetime-metrics updater loop (runs in every
  worker → identical values for `mostrecent`); all `ChannelType` values set (0 when none active).
- `registry_size`: `mostrecent` (a per-reduce snapshot; `livesum` would sum unrelated values).
- `circuit_breaker_*`: `livemax` (drops dead-worker artifacts vs plain `max`).

## Consequences

**Positive**:
- ✅ Accurate multi-worker metrics; no more bind warnings; dashboards correct (no ×N).
- ✅ Dev (single-worker) behaviour is byte-identical (multiprocess inactive).

**Negative / limitations**:
- ⚠️ `process_*` / `python_gc_*` default collectors are **absent** from the aggregated endpoint
  (a `MultiProcessCollector` limitation). No Grafana dashboard uses them; container/system
  metrics come from cAdvisor + node-exporter.
- ⚠️ `llm_cost_by_model/node_last_24h`: a model that drops out of the 24h window may retain a
  stale label value until the next deploy (`._metrics.clear()` is per-process). Minor accuracy
  loss on 2 piecharts; self-heals on redeploy.
- ⚠️ `registry_size` remains a per-reduce snapshot, not a true live count — a faithful metric
  would need an add/remove (`inc`/`dec`) lifecycle (out of scope, recommended separately).

**Risks mitigated**:
- ⚠️ `/dev/shm` is 64 MB by default; measured footprint is **~824 KB** for 4 workers (75× margin).
  Override `PROMETHEUS_MULTIPROC_DIR` or bump `shm_size` if cardinality grows materially.

## Validation

- Mechanism test (4 modes + `mark_process_dead`): counter sums, `mostrecent`=single value,
  `livesum`=sum, `livemax`=max, cleanup drops a marked-dead worker.
- Real-gauge test (`metrics_database`): `pool_size` (mostrecent)=single series, `checkedout`
  (livesum)=sum.
- End-to-end real 2-worker app: **0 series carrying a `pid=` label across 1874 series**
  (no per-worker duplication), aggregated endpoint served, footprint 824 KB.
- `ruff` / `black` / `mypy` (strict) green; 4 Grafana metric query contracts preserved.

## Related Decisions

- [ADR-020: Triple-Layer Observability Stack](ADR-020-Observability-Stack.md)
- [ADR-063: Cross-Worker Cache Invalidation via Redis Pub/Sub](ADR-063-Cross-Worker-Cache-Invalidation.md)

## References

- [prometheus_client multiprocess mode](https://prometheus.github.io/client_python/multiprocess/)
- Code: `apps/api/docker-entrypoint.sh`, `apps/api/src/main.py`, `apps/api/src/infrastructure/observability/*.py`
- Metric catalogue: `docs/technical/METRICS_REFERENCE.md`
