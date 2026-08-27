# Prometheus Alert Thresholds — Environment Configuration

## Overview

Alert thresholds are **externalized per environment** and rendered into Prometheus rule files with Jinja2. Since ADR-119 (2026-07), only the **14-alert core** (`alerts-core.yml`) is loaded by Prometheus; the legacy rule files are kept as recalibration material but are **not** wired into `rule_files`.

## Architecture

```
thresholds/
  ├── production.env               ← Live values (edited manually)
  ├── staging.env
  └── development.env
        ↓
*.yml.template files               ← Jinja2 templates (triple-chevron variables)
  ├── alerts-core.yml.template     ← 14-alert core (ADR-119) — LOADED
  ├── alerts.yml.template          ← legacy 60 alerts — NOT loaded
  └── alert_rules.yml.template     ← legacy 11 alerts — NOT loaded
        ↓
prepare_config.sh [environment]    ← Renders all three via render_alerts.py
        ↓
alerts-core.yml                    ← Committed artifact, mounted read-only in
                                     both docker-compose files, loaded via
                                     rule_files in prometheus.yml
```

## Workflow

After changing a threshold in `thresholds/{environment}.env`:

```bash
cd infrastructure/observability/prometheus
./prepare_config.sh production      # renders alerts-core.yml + legacy files
# promtool validation (see below), then commit .env + rendered files together
```

`render_alerts.py` uses `StrictUndefined` — a template variable missing from the
`.env` file fails the render loudly instead of producing a silent hole.

### Validation

```bash
docker run --rm --entrypoint promtool \
  -v "$(pwd)/infrastructure/observability/prometheus:/cfg" prom/prometheus:v3.0.0 \
  check rules /cfg/alerts-core.yml
```

## Core thresholds (`ALERT_CORE_*`)

The `ALERT_CORE_*` block at the top of each `thresholds/*.env` file feeds
`alerts-core.yml.template`. Rules for these values:

- **They are live in production** — treat every change like a production change.
- Descriptions in the template reference the **same variables** as expressions,
  so displayed thresholds can never drift from firing thresholds.
- `ALERT_CORE_SSE_TTFT_P95_SECONDS` is deliberately set **above the measured
  production baseline** (TTFT p95 16–57s) to catch degradation, not to enforce
  an aspirational SLA. Tighten it after the latency-optimization work lands.

## ⚠️ Legacy thresholds are corrupted (ADR-119)

The former `generate_threshold_envs.py` generator (deleted 2026-07) applied
blind multipliers (production ×1.5, staging ×3, development ×7.5) to every
baseline — **including bounded percentages**. Examples still present in the
legacy sections of the `.env` files:

| Variable | Rendered value | Reality |
|---|---|---|
| `ALERT_DISK_SPACE_CRITICAL_THRESHOLD` (prod) | `147.0` | disk % cannot exceed 100 — the alert could never fire |
| `ALERT_HIGH_CPU_USAGE_THRESHOLD` (prod) | `142.5` | same |
| `ALERT_HIGH_ERROR_RATE_THRESHOLD` (prod) | `30.0` | documented intent was 5% |

**Any legacy alert group must have its thresholds manually recalibrated before
being re-added to `rule_files`.** The rendered legacy files (`alerts.yml`,
`alert_rules.yml`, `alerts/*.yml`) exist only as recalibration material.

## History

- **2025-11**: thresholds externalized; one-shot migration scripts
  (`generate_threshold_envs.py`, `convert_*`, `extract_*`, `templatize_*`, …)
  lived in this directory.
- **2026-01-16**: alerting disabled entirely (never recorded in an ADR).
- **2026-07-10 (ADR-119)**: alerting re-enabled with the 14-alert core; the
  one-shot scripts and `.original/.rendered/.production` archives were deleted
  (recoverable from git history); corrupted legacy thresholds documented.
