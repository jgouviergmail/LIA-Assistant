# Observability Infrastructure - LIA

**As of 2026-07-17**: The Grafana fleet is complete, readable and honest. All 419 code-defined metrics (637 exported series) are referenced by at least one panel — dashboards 23 (Journals & User Model), 24 (Telephony) and 25 (Today Briefing) close the last blind feature families, and ten coverage sections surface the semantic guard, background runs, per-stage TTFT latency, LLM-cache savings and tool-registry integrity. Error-rate recording rules synthesize an explicit 0 instead of an empty result in the zero-error nominal state (`or vector(0)` doctrine); a nuanced `noValue` convention distinguishes true zeros (event counters) from never-computed ratios (`n/a`) while core-throughput panels keep "No data" as an outage signal; ~550 panel descriptions are generated from the metrics' own help strings. The whole fleet is audit-verified live against both production and dev Prometheus (0 query typos, 0 errors). The Prometheus metrics server runs on a dedicated HTTP-only port (9091) separate from the main HTTPS API (8000).

**Version**: 4.1 (2026-07-17)
**Status**: Production-Ready
**Architecture**: Prometheus + Grafana + Loki + Tempo + AlertManager
**Total Metrics**: 635 definitions in the backend's metric modules
**Dashboards**: one JSON per dashboard in `infrastructure/observability/grafana/dashboards/`, catalogued with their panels in [GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md)
**Alert Rules**: the active core set, `alerts-core.yml` (ADR-119; legacy set pending recalibration)
**Recording Rules**: 86 optimized rules
**Runbooks**: one per alert in `docs/runbooks/alerts/` (named after it), the procedures in `docs/runbooks/`

---

## 📋 Table of Contents

1. [Overview](#-overview)
2. [Architecture](#-architecture)
3. [Quick Start](#-quick-start)
4. [Components](#-components)
5. [Metrics Instrumentation](#-metrics-instrumentation)
6. [Dashboards](#dashboards)
7. [Alerting](#-alerting)
8. [Recording Rules](#-recording-rules)
9. [Data Retention](#-data-retention)
10. [Security & Access](#-security--access)
11. [Performance & Scaling](#-performance--scaling)
12. [Troubleshooting](#-troubleshooting)
13. [Best Practices](#-best-practices)
14. [References](#-references)

---

## 📊 Overview

### What is Observability?

Observability is the ability to measure the internal states of a system by examining its outputs. For LIA, this means:

- **Metrics** (Prometheus): Numerical measurements over time (CPU, memory, request rates, LLM costs)
- **Logs** (Loki): Discrete events with context (errors, user actions, API calls)
- **Traces** (Tempo): Request flows through distributed systems (end-to-end latency, bottlenecks)
- **Alerts** (AlertManager): Proactive notifications when thresholds are breached

### Stack Statistics

| Component | Purpose | Metrics | Retention | Port |
|-----------|---------|---------|-----------|------|
| **Prometheus** | Metrics collection & storage | 635 custom metrics (scraped from :9091) | 15 days (dev), 7 (prod) | 9090 |
| **Grafana** | Visualization & dashboards | catalogued in [GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md) | N/A (queries only) | 3000 |
| **Loki** | Log aggregation & storage | N/A (logs, not metrics) | 7 days | 3100 |
| **Tempo** | Distributed tracing | Trace spans | 7 days | 3200 |
| **AlertManager** | Alert routing & notifications | core alert set loaded (ADR-119); legacy catalog quarantined | N/A (stateful) | 9093 |
| **blackbox-exporter** | HTTP probes (backup healthcheck, public URL/TLS) | 2 probe jobs | N/A (stateless) | 9115 |

### Metrics Breakdown by Category

| Category | Key metrics | Dashboard |
|----------|-------------|-----------|
| **Agent orchestration** | `router_latency_seconds`, `graph_exceptions_total` | [07-agents-pipeline](../../infrastructure/observability/grafana/dashboards/07-agents-pipeline.json) |
| **Answer latency** | `sse_time_to_first_token_seconds` | [01-app-overview](../../infrastructure/observability/grafana/dashboards/01-app-overview.json) |
| **LLM tokens & cost** | `llm_tokens_consumed_total`, `llm_cost_total`, `llm_api_calls_total` | [05-llm-tokens-cost](../../infrastructure/observability/grafana/dashboards/05-llm-tokens-cost.json) |
| **HITL** | `hitl_classification_method_total`, `hitl_for_each_decisions_total` | [08-hitl](../../infrastructure/observability/grafana/dashboards/08-hitl.json) |
| **Checkpoints** | `checkpoint_save_duration_seconds` | [14-registry-checkpoints](../../infrastructure/observability/grafana/dashboards/14-registry-checkpoints.json) |
| **OAuth & connectors** | `oauth_callback_total`, `oauth_pkce_validation_total` | [10-oauth-connectors-mcp](../../infrastructure/observability/grafana/dashboards/10-oauth-connectors-mcp.json) |
| **HTTP/API** | `http_requests_total`, `http_request_duration_seconds` | [04-http-api](../../infrastructure/observability/grafana/dashboards/04-http-api.json) |
| **Infrastructure** | `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes` (node-exporter) | [03-infra-resources](../../infrastructure/observability/grafana/dashboards/03-infra-resources.json) |
| **Product value** | `product_activation_rate`, `product_retention_rate`, `user_active_daily_gauge` | [26-product-value](../../infrastructure/observability/grafana/dashboards/26-product-value.json) |
| **Usage & geolocation** | `conversation_created_total`, `http_requests_by_country_total` | [17-user-analytics-geo](../../infrastructure/observability/grafana/dashboards/17-user-analytics-geo.json) |

The total is the derived count at the top of this guide. Every dashboard, and the
metrics each of its panels reads, is in the catalogue
[GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md).

---

## 🏗️ Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           LIA API                                 │
│                         (FastAPI + LangGraph)                            │
│                                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   Metrics    │  │     Logs     │  │    Traces    │                  │
│  │ :9091/metrics│  │  (Logging)   │  │   (OTLP)     │                  │
│  │ (HTTP-only)  │  │              │  │              │                  │
│  │ Prometheus   │  │   Handler    │  │  Exporter    │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
└─────────┼──────────────────┼──────────────────┼──────────────────────────┘
          │                  │                  │
          │ (HTTP Pull)      │ (HTTP Push)      │ (gRPC/HTTP Push)
          │ :15s             │ Real-time        │ Real-time
          ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Prometheus    │  │      Loki       │  │      Tempo      │
│   (Storage)     │  │   (Storage)     │  │   (Storage)     │
│                 │  │                 │  │                 │
│ - Time-series   │  │ - Log streams   │  │ - Trace spans   │
│ - Recording     │  │ - Label index   │  │ - Service       │
│   rules         │  │ - Compaction    │  │   graphs        │
│ - Alert eval    │  │                 │  │                 │
│   (core set)    │  │                 │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                     │
         │ (Alert firing)     │                     │
         ▼                    │                     │
┌─────────────────┐           │                     │
│  AlertManager   │           │                     │
│                 │           │                     │
│ - Routing       │           │                     │
│ - Inhibition    │           │                     │
│ - Grouping      │           │                     │
│ - Multi-channel │           │                     │
│   (Email/Slack/ │           │                     │
│    PagerDuty)   │           │                     │
└─────────────────┘           │                     │
                              │                     │
         ┌────────────────────┴─────────────────────┘
         │ (PromQL/LogQL/TraceQL queries)
         ▼
┌─────────────────────────────────────────────────────────────┐
│                         GRAFANA                              │
│                    (Visualization)                           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Datasources │  │  Dashboards  │  │    Alerts    │     │
│  │              │  │              │  │              │     │
│  │ - Prometheus │  │ provisioned  │  │ Email/Slack  │     │
│  │ - Loki       │  │ dashboards   │  │ integration  │     │
│  │ - Tempo      │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │         Datasource Correlation                   │       │
│  │  Metrics → Traces (exemplars)                    │       │
│  │  Logs → Traces (trace_id extraction)             │       │
│  │  Traces → Logs (span attributes)                 │       │
│  └──────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

#### 1. Metrics Collection (Pull Model)

```
API :9091/metrics (HTTP-only)
        ↓ (HTTP GET every 15s)
Prometheus scraper
        ↓ (Time-series storage)
TSDB (Prometheus storage)
        ↓ (PromQL queries)
Grafana dashboards
```

**Metrics Exposed** (a few of the metric modules):
- `metrics.py` (HTTP, infrastructure, business)
- `metrics_agents.py` (LangGraph, router, SSE streaming, HITL)
- `metrics_llm.py` (tokens, cost, API calls)
- `metrics_conversations.py` (checkpoints, messages)
- `metrics_oauth.py` (OAuth 2.1 security)
- `metrics_connectors.py` (Gmail, Google Contacts)

#### 2. Logs Collection (Push Model)

```
Application logging
        ↓ (JSON structured logs)
Loki HTTP API
        ↓ (Label indexing + compression)
Loki storage (chunks + index)
        ↓ (LogQL queries)
Grafana dashboards
```

**Log Labels**:
- `job`: Service name (e.g., `lia-api`)
- `level`: Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- `logger_name`: Python logger name (e.g., `agents.router`)
- `trace_id`: OpenTelemetry trace ID (for correlation)

#### 3. Traces Collection (Push Model)

```
OTLP exporter in app
        ↓ (gRPC/HTTP)
Tempo receiver
        ↓ (Span storage + service graph generation)
Tempo storage
        ↓ (TraceQL queries)
Grafana dashboards
```

**Trace Attributes**:
- `service.name`: `lia-api`
- `http.method`, `http.route`, `http.status_code`
- `db.statement`, `db.system` (PostgreSQL queries)
- `llm.model`, `llm.tokens` (LLM API calls)

#### 4. Alert Evaluation & Notification

```
Prometheus evaluates alert rules (every 30s-1m)
        ↓ (Alert fires if condition true for `for` duration)
AlertManager receives alert
        ↓ (Deduplication, grouping, inhibition)
Routing tree evaluation
        ↓ (Label matching)
Receiver selection (critical/warning, then the agents/security audiences)
        ↓ (Template rendering)
Multi-channel notification
        ↓
Email + Slack + PagerDuty (depending on severity/component)
```

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose installed
- Ports available: 3000 (Grafana), 9090 (Prometheus), 9093 (AlertManager), 3100 (Loki), 3200 (Tempo)
- SMTP credentials for email alerts (Gmail App Password recommended)

### 1. Clone & Navigate

```bash
cd d:\Developpement\LIA
```

### 2. Configure Environment Variables

Create `.env.alerting` for AlertManager:

```bash
cd apps/api
cp .env.alerting.example .env.alerting
```

Edit `.env.alerting`:

```bash
# SMTP Configuration (Gmail example)
ALERTMANAGER_SMTP_FROM="alerts@lia.com"
ALERTMANAGER_SMTP_SMARTHOST="smtp.gmail.com:587"
ALERTMANAGER_SMTP_AUTH_USER="your-email@gmail.com"
ALERTMANAGER_SMTP_AUTH_PASSWORD="your-16-char-app-password"
ALERTMANAGER_EMAIL_TO_CRITICAL="ops-critical@lia.com"
ALERTMANAGER_EMAIL_TO_WARNING="ops@lia.com"

# Optional: Slack integration
ALERTMANAGER_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Optional: PagerDuty integration
ALERTMANAGER_PAGERDUTY_SERVICE_KEY="your-pagerduty-integration-key"
```

**Gmail App Password Setup**:
1. Enable 2FA: https://myaccount.google.com/security
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use 16-character password (not your regular password)

### 3. Start the Observability Stack

```bash
# From project root
docker-compose up -d prometheus grafana loki tempo alertmanager
```

**Services Started**:
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Loki: http://localhost:3100
- Tempo: http://localhost:3200
- AlertManager: http://localhost:9093

### 4. Start the API (with metrics instrumentation)

```bash
docker-compose up -d api
```

**Metrics Endpoint**: http://localhost:8000/metrics

### 5. Verify Setup

```bash
# 1. Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Expected output:
# {"job": "prometheus", "health": "up"}
# {"job": "lia-api", "health": "up"}
# {"job": "postgresql", "health": "up"}
# {"job": "redis", "health": "up"}

# 2. Check Grafana datasources
curl -s http://admin:admin@localhost:3000/api/datasources | jq '.[] | {name: .name, type: .type, url: .url}'

# Expected: Prometheus, Loki, Tempo datasources

# 3. Check AlertManager health
curl http://localhost:9093/-/healthy
# Expected: "Healthy"

# 4. Query sample metric
curl -s 'http://localhost:9090/api/v1/query?query=up' | jq '.data.result[] | {instance: .metric.instance, value: .value[1]}'
```

### 6. Access Grafana Dashboards

1. Navigate to http://localhost:3000
2. Login: `admin` / `admin` (change on first login)
3. Go to **Dashboards**: every dashboard of `infrastructure/observability/grafana/dashboards/`
   is provisioned there, at the root, numbered by domain (`01 - Application Overview`,
   `05 - LLM Tokens & Cost`, …); the **LIA dashboards** menu of each one opens the others
4. What each dashboard shows, panel by panel: [GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md)

### 7. Test Alerting

Send a test alert to verify email delivery:

```bash
curl -X POST http://localhost:9093/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "component": "test"
    },
    "annotations": {
      "summary": "Test alert from LIA",
      "description": "Verifying AlertManager email configuration"
    },
    "startsAt": "2025-11-22T10:00:00Z"
  }
]'
```

**Expected**: Email received at `ALERTMANAGER_EMAIL_TO_WARNING` within 1 minute

---

## 🔧 Components

### 1. Prometheus (Metrics Storage & Alerting)

**Location**: `infrastructure/observability/prometheus/`

**Purpose**: Time-series database for metrics collection, storage, and alerting.

#### Configuration Files

##### prometheus.yml (Main Configuration)

**File**: `infrastructure/observability/prometheus/prometheus.yml`: the jobs it scrapes
(the API on its metrics port 9091, the containers through cAdvisor, PostgreSQL, Redis,
the node, the observability stack itself on keep-lists — ADR-333 — and the blackbox
probes) and the two rule files it loads, `recording_rules.yml` and the core alerts
`alerts-core.yml` (ADR-119); the legacy `alerts.yml` and `rules/*.yml` stay commented
out. The file is the reference; this guide does not restate it.

**Retention**: `--storage.tsdb.retention.time` in the compose files — 15 days in dev,
7 in production.

##### recording_rules.yml

See the *Recording Rules* section below.

##### alerts-core.yml (the alerts Prometheus loads)

The core alert set (ADR-119), rendered from `alerts-core.yml.template` with each
environment's thresholds and tested rule by rule with `promtool` (`task test:alerts`,
`infrastructure/observability/prometheus/tests/alerts_core_test.yml`); every alert
links to its runbook under `docs/runbooks/alerts/`. Operational guide:
[ALERTING.md](../technical/ALERTING.md).

##### alerts.yml and alert_rules.yml (legacy, not loaded)

The 2025-11 design, commented out in `prometheus.yml` until it is recalibrated (see
the *Alerting* section below).

#### Data Storage

**Location**: Docker volume `prometheus_data`

**Structure**:
```
/prometheus/
├── chunks_head/          # Recent data (hot storage)
├── wal/                  # Write-Ahead Log (crash recovery)
├── 01JB.../              # 2-hour blocks (compacted)
│   ├── chunks/
│   ├── index
│   └── meta.json
└── queries.active        # Active queries log
```

**Retention**: 15 days in dev, 7 in production (`--storage.tsdb.retention.time` in the compose files)

**Disk Usage Estimation**:
- ~500MB per day for 150 metrics scraped every 15s
- 15 days retention (dev) = ~7.5GB total

#### Prometheus UI Features

**URL**: http://localhost:9090

**Key Features**:
1. **Graph**: PromQL query interface
2. **Alerts**: View active/pending/firing alerts
3. **Targets**: Scrape target health status
4. **Rules**: Recording & alert rules status
5. **Service Discovery**: Discovered targets
6. **Configuration**: Current config (read-only)
7. **Flags**: Startup flags
8. **Status**: TSDB status, retention, cardinality

**Useful Queries**:
```promql
# Cardinality (number of unique time series)
count({__name__=~".+"})

# Scrape duration by job
scrape_duration_seconds{job="lia-api"}

# Top 10 metrics by cardinality
topk(10, count by (__name__)({__name__=~".+"}))
```

---

### 2. Grafana (Visualization & Dashboards)

**Location**: `infrastructure/observability/grafana/`

**Purpose**: Unified visualization platform for metrics, logs, and traces.

#### Datasources Configuration

**Location**: `grafana/provisioning/datasources/datasources.yml`

##### Prometheus Datasource

```yaml
- name: Prometheus
  type: prometheus
  access: proxy
  url: http://prometheus:9090
  isDefault: true
  jsonData:
    timeInterval: 15s
    queryTimeout: 60s
    httpMethod: POST
    exemplarTraceIdDestinations:
      - name: trace_id
        datasourceUid: tempo
        urlDisplayLabel: View Trace
```

**Features**:
- Default datasource for all dashboards
- Exemplars support (metrics → traces correlation)
- POST method for large queries

##### Loki Datasource

```yaml
- name: Loki
  type: loki
  access: proxy
  url: http://loki:3100
  jsonData:
    maxLines: 1000
    derivedFields:
      - datasourceUid: tempo
        matcherRegex: "trace_id=(\\w+)"
        name: TraceID
        url: '$${__value.raw}'
```

**Features**:
- Log → Trace correlation via `trace_id` extraction
- Max 1000 lines per query (adjustable)

##### Tempo Datasource

```yaml
- name: Tempo
  type: tempo
  access: proxy
  url: http://tempo:3200
  jsonData:
    tracesToLogs:
      datasourceUid: loki
      tags: ['job', 'instance']
      mappedTags:
        - key: service.name
          value: job
      filterByTraceID: true
      filterBySpanID: false
    tracesToMetrics:
      datasourceUid: prometheus
      tags: [{ key: 'service.name', value: 'job' }]
      queries:
        - name: 'Request Rate'
          query: 'rate(http_requests_total{$$__tags}[5m])'
```

**Features**:
- Trace → Logs correlation (automatic filtering)
- Trace → Metrics correlation (RED metrics)
- Service graph visualization

#### Dashboards

**Location**: `infrastructure/observability/grafana/dashboards/`, one JSON file per
dashboard, provisioned at the root of Grafana's **Dashboards** page and numbered by
domain.

**Catalogue**: every dashboard, its rows, its panels and the metrics each panel reads,
in [GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md). This guide does not
restate it: kept in two places, the list drifted here, where dashboards were still
described under their former names and panel counts long after they were renumbered.

**Conventions** (ADR-333, held by `apps/api/tests/unit/test_grafana_dashboard_conventions_guard.py`):

- a dashboard opens on the last **7 days** and refreshes every **5 minutes**; the logs
  and traces dashboard ([06-logs-traces](../../infrastructure/observability/grafana/dashboards/06-logs-traces.json)) opens on **4 hours**;
- every dashboard carries the same **LIA dashboards** menu, listing every dashboard
  tagged `lia`; a link does not carry the time range, so each one opens on its own;
- every metric the backend defines is read by a panel, a recording rule or an alert
  (`apps/api/tests/unit/test_metric_coverage_ratchet_guard.py`); a counter watched for
  a rare event reads `or vector(0)` with `"noValue": "0"`, so a quiet one shows 0, not
  « No data ».

### 3. Loki (Log Aggregation)

**Location**: `infrastructure/observability/loki/`

**Purpose**: Horizontally-scalable log aggregation system (like Prometheus, but for logs).

#### Configuration

**File**: `loki/loki-config.yml`

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/boltdb-shipper-active
    cache_location: /loki/boltdb-shipper-cache
    shared_store: filesystem
  filesystem:
    directory: /loki/chunks

limits_config:
  retention_period: 168h  # 7 days
  ingestion_rate_mb: 4
  ingestion_burst_size_mb: 6
  max_streams_per_user: 10000
  max_query_length: 721h  # 30 days

chunk_store_config:
  max_look_back_period: 168h  # 7 days

compactor:
  working_directory: /loki/compactor
  shared_store: filesystem
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
```

**Key Settings**:
- **Retention**: 7 days (`retention_period: 168h`)
- **Ingestion Rate**: 4MB/s (burst: 6MB/s)
- **Compaction**: Every 10 minutes (reduces storage)
- **Max Streams**: 10,000 per user
- **Storage**: Local filesystem (BoltDB for index, filesystem for chunks)

#### Log Labels

Labels in Loki are indexed - use sparingly for high cardinality data.

**Standard Labels**:
- `job`: Service name (e.g., `lia-api`)
- `level`: Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- `logger_name`: Python logger name (e.g., `agents.router`, `api.endpoints.users`)
- `instance`: Container instance (e.g., `api:8000`)

**Derived Labels** (extracted at query time):
- `trace_id`: OpenTelemetry trace ID (for correlation)
- `user_id`: User ID (if present in log message)
- `endpoint`: HTTP endpoint (e.g., `/api/v1/agents/chat`)

#### LogQL Query Examples

```logql
# All logs from API
{job="lia-api"}

# Error logs only
{job="lia-api"} | json | level="ERROR"

# Logs with trace ID
{job="lia-api"} | json | trace_id != ""

# Router decision logs
{job="lia-api", logger_name="agents.router"} | json | line_format "{{.message}}"

# Logs rate per minute
sum(rate({job="lia-api"}[1m]))

# Top 10 error messages in last hour
topk(10, sum(count_over_time({job="lia-api"} | json | level="ERROR" [1h])) by (message))

# HTTP 5xx errors
{job="lia-api"} | json | status_code >= 500

# Logs for specific user
{job="lia-api"} | json | user_id="abc123"
```

#### Data Storage

**Location**: Docker volume `loki_data`

**Structure**:
```
/loki/
├── chunks/                # Log chunks (compressed)
├── boltdb-shipper-active/ # Active index
├── boltdb-shipper-cache/  # Index cache
├── compactor/             # Compaction working directory
└── rules/                 # LogQL alert rules (optional)
```

**Disk Usage Estimation**:
- ~50MB per day for typical application logs (compressed)
- 7 days retention = ~350MB total

---

### 4. Tempo (Distributed Tracing)

**Location**: `infrastructure/observability/tempo/`

**Purpose**: Distributed tracing backend (OpenTelemetry compatible).

#### Configuration

**File**: `tempo/tempo.yml`

```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318
    jaeger:
      protocols:
        thrift_http:
          endpoint: 0.0.0.0:14268
    zipkin:
      endpoint: 0.0.0.0:9411

ingester:
  max_block_duration: 5m

compactor:
  compaction:
    block_retention: 168h  # 7 days

storage:
  trace:
    backend: local
    local:
      path: /var/tempo/blocks
    wal:
      path: /var/tempo/wal
    pool:
      max_workers: 100
      queue_depth: 10000

metrics_generator:
  registry:
    external_labels:
      source: tempo
      cluster: lia
  storage:
    path: /var/tempo/generator/wal
    remote_write:
      - url: http://prometheus:9090/api/v1/write
        send_exemplars: true
  traces_storage:
    path: /var/tempo/generator/traces

overrides:
  defaults:
    metrics_generator:
      processors:
        - service-graphs
        - span-metrics
```

**Key Features**:
- **Receivers**: OTLP (gRPC:4317, HTTP:4318), Jaeger, Zipkin
- **Retention**: 7 days
- **Metrics Generator**: Generates RED metrics (Rate, Errors, Duration) from traces
- **Service Graphs**: Automatic service dependency mapping
- **Exemplars**: Trace samples attached to metrics (metrics → traces correlation)

#### Trace Attributes

**Standard OpenTelemetry Attributes**:
- `service.name`: `lia-api`
- `http.method`: `GET`, `POST`, etc.
- `http.route`: `/api/v1/agents/chat`
- `http.status_code`: `200`, `500`, etc.
- `http.target`: the route template (`/api/v1/relations/favorites/{name}`), never the concrete path nor the query (`unmatched` for a request no route matched)
- `db.system`: `postgresql`
- `db.statement`: SQL query (sanitized)

**Custom Attributes**:
- `llm.model`: `gpt-4.1-mini-mini`, `claude-3-5-sonnet-20241022`
- `llm.tokens.prompt`: Prompt tokens count
- `llm.tokens.completion`: Completion tokens count
- `llm.cost.usd`: Cost in USD
- `agent.intention`: `email_search`, `document_query`, etc.
- `agent.node_name`: LangGraph node name
- `user_id`: User ID (if authenticated)

#### TraceQL Query Examples

```traceql
# All traces from API
{service.name="lia-api"}

# Traces with HTTP 500 errors
{service.name="lia-api" && http.status_code >= 500}

# Traces with LLM calls
{service.name="lia-api" && llm.model != nil}

# Slow traces (>5s duration)
{service.name="lia-api" && duration > 5s}

# Traces for specific user
{service.name="lia-api" && user_id="abc123"}

# PostgreSQL queries
{service.name="lia-api" && db.system="postgresql"}
```

#### Data Storage

**Location**: Docker volume `tempo_data`

**Structure**:
```
/var/tempo/
├── traces/           # Trace blocks (compressed)
├── wal/              # Write-Ahead Log
└── generator/
    ├── wal/          # Metrics generator WAL
    └── traces/       # Generator traces
```

**Disk Usage Estimation**:
- ~100MB per day for typical trace volume
- 7 days retention = ~700MB total

---

### 5. AlertManager (Alert Routing & Notification)

**Location**: `infrastructure/observability/alertmanager/`

**Purpose**: Handle alerts from Prometheus, deduplicate, group, and route to notification channels.

Operational guide, rendering and the routing actually deployed: [ALERTING.md](../technical/ALERTING.md).

#### Alert Rules Summary

The groups below are the **legacy 2025-11 catalog**, not loaded: Prometheus
loads `alerts-core.yml` alone (ADR-119).

**Total**: 57 alert rules across 9 groups

| Group | Alerts | Purpose |
|-------|--------|---------|
| `hitl_quality` | 10 | HITL classifier, edits, rejections quality |
| `agents_langgraph_alerts` | 5 | Agent SLA violations (TTFT, tokens/s, router) |
| `conversations` | 6 | Checkpoint performance, conversation metrics |
| `tokens_and_cost` | 8 | LLM API failures, cost budgets, token consumption |
| `oauth_alerts` | 6 | OAuth security, PKCE validation, callback performance |
| `redis_rate_limiting_alerts` | 9 | Rate limiting hit rates, latency, errors |
| `redis_alerts` | 3 | Redis uptime, memory, connections |
| `database_alerts` | 4 | PostgreSQL connections, slow queries |
| `application_alerts` + `infrastructure_alerts` | 11 | HTTP errors, latency, disk, CPU, memory |

#### Routing Tree

Severity fixes the urgency (the backend team); the component adds an audience
(a team with an address of its own, told in addition). Every block for a
channel or a team that is not configured is left out at rendering.

```
Default route → default-email (an alert no child matches)
│
├─ (LIA webhook, when configured: every critical/warning, continue)
├─ severity: critical → critical (Email + Slack critical + PagerDuty), continue
├─ severity: warning → warning (Email + Slack warning), continue
│
├─ component: agents | hitl | hitl_streaming → ml-team (Email)
└─ component: oauth, severity: critical → security-team (Email and/or Slack security)
```

#### Email Templates

**Specialized templates** (`templates/email.tmpl`):
1. `email.default.html` - Generic alerts
2. `email.critical.html` - High-priority alerts (red header, action checklist)
3. `email.warning.html` - Warning alerts (orange header)
4. `email.agents.html` - Agent SLA violations (runbook emphasis)
5. `email.security.html` - OAuth security incidents (security warning box)

---

## 📈 Metrics Instrumentation

### Metrics Inventory

**Total**: the derived count at the top of this guide.

Every metric is defined once, in `apps/api/src/infrastructure/observability/`:
`metrics.py` (HTTP and the application's own gauges), `metrics_agents.py` (graph,
router, streaming, LLM tokens and cost, HITL) and one module per domain beside them
(`metrics_oauth.py`, `metrics_product.py`, `metrics_prompt_cache.py`, …); a few live
with the code they measure (the checkpointer's, in
`apps/api/src/domains/conversations/checkpointer.py`). What each one counts, and its
labels: [METRICS_REFERENCE.md](../technical/METRICS_REFERENCE.md); which dashboard
reads it: the table *Metrics Breakdown by Category* above and
[GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md). This guide quotes no
definition: the module is the definition, and the copies kept here had drifted — a
third of the metrics they quoted no longer existed.

#### Multi-worker aggregation (multiprocess)

Prod runs `uvicorn --workers 4`. Metrics are aggregated **across workers** via `prometheus_client`
multiprocess mode — `PROMETHEUS_MULTIPROC_DIR` is set by `docker-entrypoint.sh` **only when
`--workers` is used** (single-worker dev with `--reload` is unaffected); the worker that binds the
metrics port (9091) serves the aggregate of all workers via `MultiProcessCollector`. Counters and
Histograms sum automatically; **every Gauge declares an explicit `multiprocess_mode`** (`mostrecent`
for shared/DB-derived values, `livesum` for per-worker resources, `livemax`/`livemin` otherwise) to
avoid per-PID series duplication. See [ADR-089](../architecture/ADR-089-Prometheus-Multiprocess-Metrics.md)
and [METRICS_REFERENCE.md](../technical/METRICS_REFERENCE.md).

#### Adding a metric

A new metric goes in the module of its domain, and the build refuses it until a panel,
a recording rule or an alert reads it
(`apps/api/tests/unit/test_metric_coverage_ratchet_guard.py`). A labelled counter that
never fired exposes no series, so a panel watching a rare event reads `or vector(0)`
with `"noValue": "0"`.

---

## 🔔 Alerting

> **Current state (ADR-119, 2026-07)**: Prometheus loads **only the core
> alert set** (`alerts-core.yml`) and delivers by **email** through Alertmanager in
> both dev and production — operational guide: [ALERTING.md](../technical/ALERTING.md).
> The alert groups catalogued below are the **legacy 2025-11 design**: NOT
> loaded, and their rendered thresholds are corrupted (recalibration required
> before re-enabling any group — see
> [PROMETHEUS_THRESHOLDS.md](../technical/PROMETHEUS_THRESHOLDS.md)).
> Slack/PagerDuty channels mentioned below are optional and unset by default
> (email-only mode).

### Alert Philosophy

Alerts should be:
1. **Actionable**: Every alert requires immediate human action
2. **Urgent**: Indicates service degradation or user impact
3. **Unique**: Not redundant with other alerts (use inhibition rules)
4. **Tuned**: Thresholds based on SLOs and baseline metrics

### Alert Severity Levels

| Severity | Response Time | Channels | Examples |
|----------|---------------|----------|----------|
| **critical** | < 15min | Email + Slack + PagerDuty | Service down, >40% error rate, PKCE validation failures |
| **warning** | < 2 hours | Email + Slack | High latency, elevated error rate, >20% rejection rate |
| **info** | Best effort | Email | High token consumption, cache size growing |

### Alert Groups

#### 1. HITL Quality (10 alerts)

**Purpose**: Monitor Human-in-the-Loop classifier and proposal quality

**Critical Alerts**:
- `HITLClarificationFallbackCritical`: Classifier fallback >40% for 5m
- `HITLRejectionRateSpike`: Rejection rate >50% for 10m

**Warning Alerts**:
- `HITLClarificationFallbackHigh`: Classifier fallback >20% for 10m
- `HITLFullRewritesHigh`: Full rewrites >30% for 30m
- `HITLExplicitRejectionsHigh`: Explicit rejections >20% for 30m
- `HITLUserResponseTimeSlow`: User response p95 >5min for 15m

#### 2. Agents LangGraph (5 alerts)

**Purpose**: Monitor agent SLA compliance

**SLAs**:
- TTFT (Time to First Token): < 1000ms
- Tokens/sec: > 20 tokens/sec
- Router latency: < 500ms
- Streaming error rate: < 5%
- Router confidence: > 0.6 (low confidence < 40%)

**Alerts**:
- `AgentsTTFTViolation` (warning): TTFT p95 >5s for 5m
- `AgentsTokensPerSecondLow` (warning): <5 tokens/s for 5m
- `AgentsRouterLatencyHigh` (critical): Router p95 >3s for 5m
- `AgentsStreamingErrorRateHigh` (critical): >25% errors for 3m
- `AgentsRouterLowConfidenceHigh` (warning): >40% low confidence for 10m

#### 3. Tokens & Cost (8 alerts)

**Purpose**: Monitor LLM API failures and cost budgets

**Alerts**:
- `LLMAPIFailureRateHigh` (critical): Error rate >30% for 5m
- `DailyCostBudgetExceeded` (critical): Daily cost >5€ for 1m
- `HourlyCostTrendingHigh` (warning): Hourly cost >1€ for 30m
- `ModelCostBudgetExceeded` (critical): Per-model cost >3€ for 1m

#### 4. OAuth Security (6 alerts)

**Purpose**: Detect OAuth attacks and configuration issues

**Critical Alerts**:
- `PKCEValidationFailures`: PKCE failures >5/s for 2m (possible CSRF attack)
- `StateTokenValidationFailures`: State failures >5/s for 2m

**Warning Alerts**:
- `HighOAuthFailureRate`: Callback failure >50% for 5m
- `SlowOAuthCallback`: Callback p95 >30s for 5m

### Inhibition Rules

Inhibition rules prevent alert spam by suppressing redundant alerts.

**Example**:
```yaml
# If ServiceDown fires, suppress HighErrorRate and HighLatency
- source_match:
    alertname: 'ServiceDown'
  target_match_re:
    alertname: '(HighErrorRate|HighLatency.*)'
  equal: ['service']
```

**All Inhibition Rules**:
1. ServiceDown → Suppress HighErrorRate/HighLatency
2. RedisDown → Suppress RedisConnectionsHigh/MemoryHigh
3. PostgreSQLDown → Suppress connection/query alerts
4. DailyBudgetExceeded → Suppress Weekly/Monthly alerts
5. Critical severity → Suppress Warning for same alert

---

## 📝 Recording Rules

**Purpose**: Pre-compute expensive queries to improve dashboard performance.

**Where**: `infrastructure/observability/prometheus/recording_rules.yml`, loaded by
Prometheus beside the core alerts (`alerts-core.yml`); the legacy `alerts.yml` and
`rules/*.yml` stay commented out in `prometheus.yml` (ADR-119). `task test:alerts`
checks both loaded files with `promtool`, and a recording rule counts as a reader of
the metrics it reads for the metric coverage guard.

**Naming**: a family, then what it computes and over which window, colon-separated —
for example `sse_ttft:p95_5m`, `business:hitl:approval_rate:1h` or
`api:slo:error_budget:remaining_30d`.

This guide quotes no rule: the file is the definition, and the copies kept here had
drifted — most of the rules they quoted no longer existed, under a total the file had
long outgrown.

---

## 💾 Data Retention

### Retention Policies

| Component | Retention | Configurable | Location |
|-----------|-----------|--------------|----------|
| **Prometheus** | 15 days (dev), 7 (prod) | Yes (`--storage.tsdb.retention.time`) | the compose files |
| **Loki** | 7 days | Yes (`retention_period`) | `loki-config.yml` |
| **Tempo** | 7 days | Yes (`block_retention`) | `tempo.yml` |
| **Grafana** | N/A (queries only) | N/A | N/A |
| **AlertManager** | N/A (stateful, not time-series) | N/A | Silences stored in memory |

### Disk Space Estimation

**Total**: ~10GB for full stack in dev (15 days Prometheus, 7 days logs/traces)

| Component | Daily Usage | 15 Days | 7 Days |
|-----------|-------------|---------|--------|
| Prometheus | ~500MB | ~7.5GB | ~3.5GB |
| Loki | ~50MB | ~750MB | ~350MB |
| Tempo | ~100MB | ~1.5GB | ~700MB |
| Grafana | ~10MB | ~150MB | ~70MB |
| **Total** | ~660MB | **~10GB** | **~4.6GB** |

### Retention Configuration Changes

#### Prometheus

Edit `docker-compose.prod.yml`:

```yaml
services:
  prometheus:
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'  # Change from 15d to 30d
```

#### Loki

Edit `loki/loki-config.yml`:

```yaml
limits_config:
  retention_period: 336h  # 14 days (change from 168h)
```

#### Tempo

Edit `tempo/tempo.yml`:

```yaml
compactor:
  compaction:
    block_retention: 336h  # 14 days (change from 168h)
```

---

## 🔐 Security & Access

### Authentication

#### Grafana

**Default Credentials**: `admin` / `admin` (change on first login)

**Production Setup**:
1. Change admin password immediately
2. Create separate user accounts for team members
3. Use LDAP/OAuth for SSO (optional)
4. Enable HTTPS (TLS certificates)

**User Roles**:
- **Admin**: Full access (dashboards, datasources, users)
- **Editor**: Create/edit dashboards, view datasources
- **Viewer**: View dashboards only (read-only)

#### Prometheus

**No authentication by default** - restrict access via:
1. Docker network isolation (internal network only)
2. Firewall rules (allow only from Grafana IP)
3. Reverse proxy with authentication (NGINX + Basic Auth)

**Production Setup**:
```yaml
# nginx.conf
location /prometheus/ {
    auth_basic "Prometheus";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://prometheus:9090/;
}
```

#### AlertManager

**No authentication by default** - same recommendations as Prometheus.

**Production Setup**: Use reverse proxy with authentication or restrict to internal network only.

### Network Security

#### Docker Network Isolation

```yaml
# docker-compose.yml
networks:
  monitoring:
    driver: bridge
    internal: true  # No external access

  public:
    driver: bridge

services:
  prometheus:
    networks:
      - monitoring  # Internal only

  grafana:
    networks:
      - monitoring  # Internal
      - public      # External (via reverse proxy)
```

#### Firewall Rules (Linux)

```bash
# Allow only Grafana to access Prometheus
iptables -A INPUT -p tcp --dport 9090 -s <grafana-ip> -j ACCEPT
iptables -A INPUT -p tcp --dport 9090 -j DROP

# Allow only localhost to access AlertManager
iptables -A INPUT -p tcp --dport 9093 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 9093 -j DROP
```

### Data Security

#### Secrets Management

**Environment Variables**:
- Use `.env` files for sensitive data (SMTP passwords, API keys)
- Never commit `.env` files to Git (add to `.gitignore`)
- Use Docker secrets in production (Swarm/Kubernetes)

**AlertManager Secrets**:
```yaml
# alertmanager.yml
smtp_auth_password: '{{ env "ALERTMANAGER_SMTP_AUTH_PASSWORD" }}'  # ✅ Good
# smtp_auth_password: 'hardcoded-password'  # ❌ Bad
```

#### TLS/SSL

**Grafana HTTPS**:

```yaml
# docker-compose.yml
services:
  grafana:
    environment:
      - GF_SERVER_PROTOCOL=https
      - GF_SERVER_CERT_FILE=/etc/grafana/ssl/cert.pem
      - GF_SERVER_CERT_KEY=/etc/grafana/ssl/key.pem
    volumes:
      - ./ssl:/etc/grafana/ssl:ro
```

**Generate Self-Signed Cert (Dev)**:
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -subj "/CN=localhost"
```

---

## ⚡ Performance & Scaling

### Query Optimization

#### 1. Use Recording Rules

**❌ Bad** (expensive query on every dashboard refresh):
```promql
histogram_quantile(0.95,
  sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (intention, le)
)
```

**✅ Good** (use pre-computed recording rule):
```promql
sse_ttft:p95_5m
```

**Savings**: ~90% query time reduction

#### 2. Reduce Cardinality

**❌ Bad** (high cardinality label):
```python
http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests",
    ["user_id"]  # ❌ Too many unique values
)
```

**✅ Good** (low cardinality labels):
```python
http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests",
    ["method", "endpoint", "status"]  # ✅ Limited unique combinations
)
```

**Rule**: Keep label cardinality < 100 unique values per metric.

#### 3. Use Efficient PromQL

**❌ Bad** (aggregates after rate):
```promql
sum(rate(http_requests_total[5m])) by (endpoint)
```

**✅ Good** (aggregates within rate):
```promql
sum(rate(http_requests_total[5m]) by (endpoint))
```

**Savings**: ~30% query time reduction for high-cardinality metrics.

### Scaling Horizontally

#### Prometheus Sharding

For >1 million active time series, consider sharding:

```yaml
# Shard 1: API metrics
scrape_configs:
  - job_name: 'lia-api'
    relabel_configs:
      - source_labels: [__name__]
        regex: '(http_.*|sse_.*|router_.*)'
        action: keep

# Shard 2: Infrastructure metrics
scrape_configs:
  - job_name: 'infrastructure'
    relabel_configs:
      - source_labels: [__name__]
        regex: '(node_.*|container_.*)'
        action: keep
```

#### Loki Horizontal Scaling

For high log volume (>100MB/s):
1. Use object storage (S3, GCS) instead of local filesystem
2. Run multiple ingesters (read/write path separation)
3. Use memcached for query caching

#### Tempo Horizontal Scaling

For high trace volume (>10k spans/s):
1. Use object storage (S3, GCS)
2. Run multiple distributors (ingestion layer)
3. Run multiple queriers (read path)

### Performance Monitoring

**Monitor the monitors**:

```promql
# Prometheus scrape duration
scrape_duration_seconds{job="lia-api"}

# Prometheus query duration p95
prometheus_engine_query_duration_seconds{quantile="0.95"}

# Loki ingestion rate
loki_ingester_streams_created_total

# Tempo ingestion rate
tempo_distributor_spans_received_total
```

---

## 🆘 Troubleshooting

### Issue 1: Prometheus Not Scraping API

**Symptoms**: Dashboards show "No data"

**Diagnosis**:
```bash
# 1. Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job == "lia-api")'

# 2. Check API /metrics endpoint
curl http://localhost:8000/metrics | head -20

# 3. Test DNS resolution
docker exec prometheus ping api
```

**Fixes**:
1. ✅ Ensure API exposes `/metrics` endpoint
2. ✅ Verify `prometheus.yml` has correct target: `api:8000`
3. ✅ Check Docker network connectivity
4. ✅ Restart Prometheus: `docker-compose restart prometheus`

---

### Issue 2: Grafana Dashboards Empty

**Symptoms**: Dashboards load but panels show "No data"

**Diagnosis**:
```bash
# 1. Check datasource health
curl -s http://admin:admin@localhost:3000/api/datasources | jq '.[] | {name: .name, type: .type, url: .url}'

# 2. Test Prometheus datasource
curl -s http://admin:admin@localhost:3000/api/datasources/proxy/1/api/v1/query?query=up | jq

# 3. Check Grafana logs
docker logs grafana | grep -i error
```

**Fixes**:
1. ✅ Verify datasource URL: `http://prometheus:9090` (not `localhost`)
2. ✅ Test datasource in Grafana UI: Configuration → Data Sources → Test
3. ✅ Check Prometheus has data: `curl 'http://localhost:9090/api/v1/query?query=up'`

---

### Issue 3: Loki Not Receiving Logs

**Symptoms**: Dashboard 09 (Logs & Traces) shows no logs

**Diagnosis**:
```bash
# 1. Test Loki API
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={job="lia-api"}' \
  | jq

# 2. Check Loki logs
docker logs loki | grep -i error

# 3. Verify API is sending logs
docker logs api | head -20
```

**Fixes**:
1. ✅ Ensure API uses structured logging (JSON format)
2. ✅ Configure Loki logging driver in `docker-compose.prod.yml`:
   ```yaml
   services:
     api:
       logging:
         driver: loki
         options:
           loki-url: "http://localhost:3100/loki/api/v1/push"
           loki-batch-size: "400"
   ```
3. ✅ Restart API: `docker-compose restart api`

---

### Issue 4: AlertManager Not Sending Emails

**Symptoms**: Alerts firing in Prometheus but no emails received

**Diagnosis**:
```bash
# 1. Check AlertManager health
curl http://localhost:9093/-/healthy

# 2. Check alerts in AlertManager
curl http://localhost:9093/api/v1/alerts | jq '.data.alerts[] | {name: .labels.alertname, state: .status.state}'

# 3. Test SMTP connection (Python)
python3 << 'EOF'
import smtplib
server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('your-email@gmail.com', 'your-app-password')
print("✅ SMTP connection successful!")
server.quit()
EOF

# 4. Check AlertManager logs
docker logs lia-alertmanager-dev | grep -i smtp   # prod : lia-alertmanager-prod
```

**Fixes**:
1. ✅ Verify `.env.alerting` has correct SMTP credentials
2. ✅ Use Gmail App Password (not regular password): https://myaccount.google.com/apppasswords
3. ✅ Check alert is not silenced: `curl http://localhost:9093/api/v1/silences`
4. ✅ Reload AlertManager config: `curl -X POST http://localhost:9093/-/reload`

---

### Issue 5: High Disk Usage

**Symptoms**: Docker volumes growing rapidly

**Diagnosis**:
```bash
# 1. Check volume sizes
docker system df -v

# 2. Check Prometheus TSDB size
docker exec prometheus du -sh /prometheus

# 3. Check cardinality (number of time series)
curl -s 'http://localhost:9090/api/v1/query?query=count({__name__=~".%2B"})' | jq
```

**Fixes**:
1. ✅ Reduce Prometheus retention: `--storage.tsdb.retention.time=7d` (instead of 15d)
2. ✅ Reduce metric cardinality (avoid high-cardinality labels like `user_id`)
3. ✅ Enable Loki compaction (already enabled, check `compaction_interval`)
4. ✅ Manually clean old data:
   ```bash
   # Remove Prometheus data older than 7 days
   docker exec prometheus promtool tsdb delete-series --match='{__name__=~".+"}' --max-time=$(date -d '7 days ago' +%s)000
   ```

---

## ✅ Best Practices

### 1. Metrics Design

**DO**:
- ✅ Use Counter for monotonically increasing values (requests, errors)
- ✅ Use Gauge for values that can go up/down (CPU%, active users)
- ✅ Use Histogram for distributions (latency, request size)
- ✅ Keep label cardinality low (< 100 unique values per label)
- ✅ Use recording rules for expensive queries
- ✅ Include units in metric names (`_seconds`, `_bytes`, `_total`)

**DON'T**:
- ❌ Use high-cardinality labels (user_id, trace_id)
- ❌ Create metrics for every function call (too granular)
- ❌ Use Summary (use Histogram instead for better query flexibility)
- ❌ Change metric labels over time (breaks time series)

### 2. Alert Design

**DO**:
- ✅ Set thresholds based on SLOs and baseline metrics
- ✅ Use multi-window evaluation (`for: 5m`) to avoid flapping
- ✅ Include actionable runbook in annotations
- ✅ Route alerts to appropriate teams via labels
- ✅ Use inhibition rules to prevent alert spam
- ✅ Test alerts before deploying to production

**DON'T**:
- ❌ Alert on everything (alert fatigue)
- ❌ Use overly sensitive thresholds (false positives)
- ❌ Alert without clear action required
- ❌ Forget to include resolution steps

### 3. Dashboard Design

**DO**:
- ✅ Use consistent time ranges across panels
- ✅ Include context (thresholds, annotations)
- ✅ Use recording rules for complex queries
- ✅ Add panel descriptions
- ✅ Group related panels together
- ✅ Test dashboards with different time ranges

**DON'T**:
- ❌ Overload dashboards (>20 panels becomes hard to read)
- ❌ Use vague panel titles ("Metric 1", "Graph 2")
- ❌ Forget to set Y-axis units
- ❌ Use heavy queries without recording rules

### 4. Data Retention

**DO**:
- ✅ Set retention based on compliance requirements
- ✅ Monitor disk usage regularly
- ✅ Use object storage for long-term retention (S3, GCS)
- ✅ Archive old data before deletion

**DON'T**:
- ❌ Keep unlimited retention (disk will fill up)
- ❌ Delete data without backup
- ❌ Forget to clean up old dashboards/alerts

### 5. Security

**DO**:
- ✅ Change default Grafana admin password
- ✅ Use environment variables for secrets
- ✅ Enable HTTPS for Grafana
- ✅ Restrict Prometheus/AlertManager to internal network
- ✅ Use RBAC (Role-Based Access Control) in Grafana
- ✅ Regularly update Docker images

**DON'T**:
- ❌ Hardcode secrets in config files
- ❌ Expose Prometheus/Loki/Tempo to public internet
- ❌ Use default credentials in production
- ❌ Share admin accounts

---

## 📚 References

### Official Documentation

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [Loki Documentation](https://grafana.com/docs/loki/latest/)
- [Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [AlertManager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)

### LIA Documentation

- Grafana Dashboards README - Exhaustive panel documentation (2330 lines)
- AlertManager README - Alert rules & routing (2494 lines)
- Metrics Inventory Analysis - Complete metrics catalog (1000+ lines)

### External Resources

- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
- [LogQL Cheat Sheet](https://megamorf.gitlab.io/cheat-sheets/loki/)
- [Grafana Dashboards Gallery](https://grafana.com/grafana/dashboards/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)

---

## 📝 Changelog

### 3.0 (2025-11-22)

**Added**:
- Complete observability infrastructure documentation (2700+ lines)
- Comprehensive architecture diagrams (metrics/logs/traces flow)
- 150+ metrics inventory with categories
- 9 dashboards documentation (116 panels)
- 57 alert rules documentation
- 65+ recording rules documentation
- Data retention policies
- Security & access control guidelines
- Performance & scaling recommendations
- Troubleshooting guide (5 common issues)
- Best practices (metrics, alerts, dashboards, retention, security)

**Changed**:
- Restructured README with 14 sections
- Added statistics tables throughout
- Expanded quick start with verification steps
- Added detailed component documentation
- Added datasource correlation documentation

**Total Lines**: 2731 (vs 307 previously - 8.9x expansion)

---

### 2.0 (2025-11-20)

- Added Conversations dashboard
- Added LLM Tokens & Cost dashboard
- Added 14 new alerts (conversations, tokens, cost)
- Updated infrastructure monitoring

---

### 1.0 (2024-01-25)

- Initial observability stack setup
- Basic Prometheus, Grafana, Loki, Tempo configuration
- 3 dashboards (Application, Infrastructure, Business)
- Basic alerting

---

## 🎯 Next Steps

After setting up the observability stack:

1. ✅ Configure environment variables (`.env.alerting`)
2. ✅ Start all services (`docker-compose up -d`)
3. ✅ Verify Prometheus targets (http://localhost:9090/targets)
4. ✅ Access Grafana dashboards (http://localhost:3000)
5. ✅ Test AlertManager email delivery
6. ✅ Review alert rules and thresholds (tune based on baseline metrics)
7. ✅ Configure Slack webhook (optional)
8. ✅ Configure PagerDuty (optional, for critical alerts)
9. ✅ Set up on-call rotation (PagerDuty schedules)
10. ✅ Create runbooks for critical alerts (external documentation)
11. ✅ Train team on Grafana UI & AlertManager silencing
12. ✅ Establish SLOs (Service Level Objectives) and monitor error budgets

**Production Readiness Checklist**:
- [ ] Change Grafana admin password
- [ ] Enable HTTPS for Grafana
- [ ] Configure backup for Prometheus data (remote write)
- [ ] Configure object storage for Loki (S3/GCS)
- [ ] Configure object storage for Tempo (S3/GCS)
- [ ] Set up AlertManager email/Slack/PagerDuty
- [ ] Create incident response runbooks
- [ ] Configure firewall rules (restrict Prometheus/Loki/Tempo to internal network)
- [ ] Set up monitoring for the monitoring stack (meta-monitoring)
- [ ] Document on-call procedures

---

**Document Maintained By**: Infrastructure Team
**Last Updated**: 2025-11-22
**Review Frequency**: Monthly
**Feedback**: Create issue in repository or contact ops-team@lia.com
