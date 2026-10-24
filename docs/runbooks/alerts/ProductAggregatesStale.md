# ProductAggregatesStale - Runbook

**Severity**: Warning
**Component**: Product analytics (dashboard 26)
**Impact**: Every figure of dashboard 26 is as old as the last completed rollup
**SLA Impact**: No — no request depends on it; the product numbers an operator reads are stale

---

## 📊 Alert Definition

**Alert Name**: `ProductAggregatesStale` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression**:
```promql
(time() - max(product_metrics_last_refresh_timestamp_seconds)) > 7200
```

`for: 15m`. The threshold comes from `ALERT_CORE_PRODUCT_AGGREGATES_STALE_SECONDS`
(`infrastructure/observability/prometheus/thresholds/*.env`): two missed hourly runs in
production.

The product figures are computed in PostgreSQL by the hourly rollup
(`infrastructure/scheduler/product_rollup.py`, job `product_analytics_rollup`, see
[ADR-178](../../architecture/ADR-178-Product-Value-Dashboard.md)): it backfills the costs,
promotes the E2 outcomes, purges past the retention, then recomputes every product gauge.
`product_metrics_last_refresh_timestamp_seconds` is stamped only when that refresh
completes WHOLE — a partial refresh keeps the previous snapshot and no new stamp — so its
age covers both ways the figures go stale: the runs fail, or the job no longer runs. A
deployment whose rollup never completed has no stamp, and the alert cannot fire there.

Moved from the unloaded `alerts-product.yml` on 2026-10-23 (audit AC-006): staleness needs
no production baseline; the product behaviour alerts left there do.

**Labels**:
- `severity`: warning
- `component`: product
- `tier`: core

---

## 🔍 Symptoms

- Dashboard 26 (product value) shows figures that no longer move, and its « Product
  aggregates freshness » panel an age past the threshold.
- The API log carries `product_rollup_failed` once per failed run, or no
  `product_rollup_completed` at all.

---

## 🎯 Possible Causes

### The runs fail
`background_job_errors_total{job_name="product_analytics_rollup"}` grows every hour: a
query of the rollup or of the gauge refresh raises — PostgreSQL unavailable, a product
migration not applied, or a defect in an aggregate.

### The job does not run
Nothing grows and no `product_rollup_completed` appears: the scheduler has no leader, or
the job was not registered on this instance.

---

## 🔧 Diagnosis

1. Failed or absent:
   ```promql
   sum(increase(background_job_errors_total{job_name="product_analytics_rollup"}[3h]))
   ```
2. A failure: read `product_rollup_failed` in Loki (`container="lia-api-prod"`), its
   traceback names the query; check `alembic current` against `alembic heads` when it is
   a missing column or table.
3. Nothing at all: look for `scheduler_elected_jobs_summary` and the job's registration in
   the API log since the last start.

---

## 🛠️ Resolution

- Database unavailable or migration missing: restore it, or apply the migrations
  (`task db:migrate` on the instance); the next hourly run refreshes every figure.
- No scheduler leader: restart the API (`docker restart lia-api-prod`), a worker takes the
  lease back.
- A defect: fix the aggregate; the figures stay at their last complete snapshot meanwhile,
  never a partial one.

---

## ✅ Verification

`product_rollup_completed` appears again in the API log, and the age above falls back
under an hour.
