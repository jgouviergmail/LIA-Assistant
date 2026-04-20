# Observability Infrastructure - LIA

**As of 2026-04-20**: Metrics and dashboards have been significantly expanded. There are now 514+ metrics, 93 recording rules, and 20 dashboards (354+ panels). Dashboards 19 (Sub-agents & Skills) and 20 (ReAct & Browser) were added to close remaining observability gaps. The Prometheus metrics server runs on a dedicated HTTP-only port (9091) separate from the main HTTPS API (8000).

**Version**: 4.0 (2025-11-23) - Phase 4 Complete
**Status**: Production-Ready
**Architecture**: Prometheus + Grafana + Loki + Tempo + AlertManager
**Total Metrics**: 500+ across 12 categories
**Dashboards**: 20 comprehensive dashboards (354+ panels)
**Alert Rules**: 100+ alerts across 15 groups
**Recording Rules**: 93 optimized rules
**Runbooks**: 22 incident response runbooks

---

## 📋 Table of Contents

1. [Overview](#-overview)
2. [Architecture](#-architecture)
3. [Quick Start](#-quick-start)
4. [Components](#-components)
5. [Metrics Instrumentation](#-metrics-instrumentation)
6. [Dashboards](#-dashboards)
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
| **Prometheus** | Metrics collection & storage | 139 custom metrics (scraped from :9091) | 15 days | 9090 |
| **Grafana** | Visualization & dashboards | 20 dashboards, 354+ panels | N/A (queries only) | 3000 |
| **Loki** | Log aggregation & storage | N/A (logs, not metrics) | 7 days | 3100 |
| **Tempo** | Distributed tracing | Trace spans | 7 days | 3200 |
| **AlertManager** | Alert routing & notifications | 57 alert rules | N/A (stateful) | 9093 |

### Metrics Breakdown by Category

| Category | Metrics Count | Key Metrics | Dashboards |
|----------|---------------|-------------|------------|
| **LLM Agents** | 35+ | `sse_time_to_first_token`, `router_latency`, `graph_exceptions` | 04 - Agents LangGraph |
| **LLM Tokens/Cost** | 20+ | `llm_tokens_consumed_total`, `llm_cost_total`, `llm_api_calls_total` | 05 - LLM Tokens & Cost |
| **HITL Tool Approval** | 18+ | `hitl_classification_method_total`, `hitl_edit_actions_total` | 07 - HITL Tool Approval |
| **Conversations** | 15+ | `conversation_active_users_total`, `checkpoint_save_duration_seconds` | 06 - Conversations |
| **OAuth 2.1 Security** | 12+ | `oauth_callback_total`, `oauth_pkce_validation_total` | 08 - OAuth Security |
| **HTTP/API** | 10+ | `http_requests_total`, `http_request_duration_seconds` | 01 - Application Performance |
| **Infrastructure** | 25+ | `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes` | 02 - Infrastructure Resources |
| **Business** | 15+ | `lia_total_users`, `lia_total_connectors` | 03 - Business Metrics |
| **GeoIP** | 1 | `http_requests_by_country_total` | 17 - User Analytics & Geo |

**Total**: 180+ metrics across 9 categories

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
│   rules (65+)   │  │ - Compaction    │  │   graphs        │
│ - Alert eval    │  │                 │  │                 │
│   (57 rules)    │  │                 │  │                 │
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
│  │ - Prometheus │  │ 20 dashboards│  │ Email/Slack  │     │
│  │ - Loki       │  │ 312+ panels  │  │ integration  │     │
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

**Metrics Exposed**: 150+ metrics across 8 Python files:
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
Receiver selection (critical/warning/budget/agents/security)
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
3. Go to **Dashboards** → **Browse**
4. Open folder **"LIA"**
5. Available dashboards:
   - 01 - Application Performance
   - 02 - Infrastructure Resources
   - 03 - Business Metrics
   - 04 - Agents LangGraph
   - 05 - LLM Tokens & Cost
   - 06 - Conversations
   - 07 - HITL Tool Approval
   - 08 - OAuth Security
   - 09 - Logs & Traces

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

```yaml
global:
  scrape_interval: 15s       # Default scrape interval
  evaluation_interval: 30s   # Alert rule evaluation frequency
  external_labels:
    cluster: 'lia'
    environment: 'production'

scrape_configs:
  # API metrics
  - job_name: 'lia-api'
    static_configs:
      - targets: ['api:9091']
    scrape_interval: 15s

  # PostgreSQL metrics
  - job_name: 'postgresql'
    static_configs:
      - targets: ['postgres_exporter:9187']

  # Redis metrics
  - job_name: 'redis'
    static_configs:
      - targets: ['redis_exporter:9121']

  # Node metrics (infrastructure)
  - job_name: 'node'
    static_configs:
      - targets: ['node_exporter:9100']

  # Container metrics
  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']

# Alert rules
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

# Recording & alert rules
rule_files:
  - '/etc/prometheus/recording_rules.yml'   # 65+ recording rules
  - '/etc/prometheus/alerts.yml'            # Infrastructure alerts
  - '/etc/prometheus/alert_rules.yml'       # HITL quality alerts
```

**Key Parameters**:
- `scrape_interval: 15s` - Balance between freshness and load
- `evaluation_interval: 30s` - Alert rule evaluation frequency
- Retention: 15 days (configurable via `--storage.tsdb.retention.time=15d`)

##### recording_rules.yml (65+ Optimized Queries)

**Purpose**: Pre-compute expensive queries to improve dashboard performance.

**Categories**:
1. **LLM Costs** (5 rules): Cost per request, tokens per request, cost by model
2. **Agent Performance** (8 rules): TTFT percentiles, tokens/sec, router latency
3. **HITL Quality** (6 rules): Approval rate, edit rate, rejection rate
4. **Conversations** (4 rules): Checkpoint save/load p99, active users
5. **HTTP** (3 rules): Request rate, error rate, latency percentiles
6. **OAuth Security** (2 rules): Callback success rate, connector API success rate
7. **Database & Infrastructure** (15+ rules): Connection pool usage, query performance
8. **SSE Streaming** (10+ rules): TTFT percentiles, streaming errors, tokens/sec by intention
9. **LLM Cache** (5 rules): Hit rate, size, evictions, latency
10. **Router** (7 rules): Confidence distribution, fallback rate, latency by intention

**Example Recording Rule**:
```yaml
# Time to First Token (TTFT) p95 by intention (5min window)
- record: sse_ttft:p95:5m
  expr: |
    histogram_quantile(0.95,
      sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (intention, le)
    )
```

**Dashboard Usage**:
Instead of running expensive `histogram_quantile()` on every dashboard refresh, use pre-computed `sse_ttft:p95:5m`.

##### alerts.yml (Infrastructure & Application Alerts)

**47 alert rules** across 6 groups:
- `application_alerts` (5 rules): Error rate, latency, service down
- `database_alerts` (4 rules): Connection pool, slow queries
- `infrastructure_alerts` (6 rules): Disk, CPU, memory, containers
- `redis_alerts` (3 rules): Redis down, memory, connections
- `redis_rate_limiting_alerts` (9 rules): Hit rates, latency, errors, Lua failures
- `agents_langgraph_alerts` (5 rules): SLA violations (TTFT, tokens/s, router)
- `conversations` (6 rules): Checkpoint performance, resets, availability
- `tokens_and_cost` (8 rules): LLM API failures, budgets, efficiency
- `oauth_alerts` (6 rules): OAuth security, PKCE validation

##### alert_rules.yml (HITL Quality Alerts)

**10 alert rules** for Human-in-the-Loop quality monitoring:
- `HITLClarificationFallbackHigh/Critical`: Classifier confidence issues
- `HITLFullRewritesHigh`: Users rewriting proposals
- `HITLEditRateIncreasing`: High edit rate
- `HITLExplicitRejectionsHigh`: Users rejecting proposals
- `HITLRejectionRateSpike`: Sudden spike in rejections
- `HITLUserResponseTimeSlow`: UX friction
- `HITLQualityDegraded`: Multiple quality indicators degraded

**Total Alert Rules**: 57 across 9 groups

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

**Retention**: 15 days (configurable)

**Disk Usage Estimation**:
- ~500MB per day for 150 metrics scraped every 15s
- 15 days retention = ~7.5GB total

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

**Location**: `infrastructure/observability/grafana/dashboards/`

**Total**: 15 dashboards, 200+ panels

For exhaustive panel-by-panel documentation, see: [Grafana Dashboards README](grafana/dashboards/README.md)

**New Dashboards (Phase 2-3)**:
- **10** - Redis Rate Limiting (Phase 2.4)
- **11** - LangGraph Framework (Phase 2.5)
- **12** - Recording Rules Health (Phase 2.2)
- **13** - SLO Tracking (Phase 2.2)
- **14** - Langfuse LLM Observability (Phase 3.1)
- **15** - Checkpoint Observability (Phase 3.3)

##### Dashboard 01 - Application Performance (2 panels)

**Purpose**: HTTP request monitoring, error rates, latency

**Key Panels**:
1. **Requests per Second by Endpoint** (Graph)
   - Query: `sum(rate(http_requests_total{job="lia-api"}[5m])) by (method, endpoint)`
   - Recording rule: `http_requests:rate:5m`

2. **HTTP Latency Percentiles** (Graph)
   - P50/P95/P99 latency
   - Query: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
   - Recording rule: `http_latency:p95:5m`

---

##### Dashboard 02 - Infrastructure Resources (20 panels)

**Purpose**: CPU, memory, disk, network, container monitoring

**Key Panels**:
- CPU Usage % (Gauge + Graph)
- Memory Usage % (Gauge + Graph)
- Disk Usage % (Gauge + Graph)
- Network I/O (Graph)
- Container Status (Table)
- PostgreSQL Connection Pool (Graph)
- Redis Memory Usage (Graph)

---

##### Dashboard 03 - Business Metrics (2 panels)

**Purpose**: User growth, connector usage, business KPIs

**Key Panels**:
1. **Total Users & Active Users** (Stat)
   - Query: `lia_total_users`, `lia_active_users`

2. **Connectors by Type** (Pie Chart)
   - Query: `lia_connectors_by_type`

---

##### Dashboard 04 - Agents LangGraph (40 panels)

**Purpose**: LangGraph execution monitoring, node performance, error tracking

**Categories**:
- **SSE Streaming Performance** (10 panels): TTFT, tokens/sec, streaming errors
- **Router Performance** (8 panels): Latency, confidence, fallback rate
- **Graph Execution** (12 panels): Node execution time, exceptions, memory usage
- **HITL Tool Approval** (10 panels): Approval rate, edit actions, rejection types

**Key Metrics**:
- `sse_time_to_first_token_seconds` (TTFT - SLA: < 1000ms)
- `sse_tokens_per_second` (SLA: > 20 tokens/sec)
- `router_latency_seconds` (SLA: < 500ms)
- `graph_exceptions_total` (monitor by node_name)

---

##### Dashboard 05 - LLM Tokens & Cost (13 panels)

**Purpose**: Token consumption, cost tracking, LLM API monitoring

**Key Panels**:
1. **Total Tokens Consumed 24h** (Stat)
   - Query: `sum(increase(llm_tokens_consumed_total[24h]))`

2. **Estimated Cost 24h** (Stat)
   - Query: `sum(increase(llm_cost_total{currency="EUR"}[24h]))`
   - Thresholds: 10€ (green), 50€ (yellow), 100€ (red)

3. **LLM API Success Rate** (Gauge)
   - Query: `sum(rate(llm_api_calls_total{status="success"}[5m])) / sum(rate(llm_api_calls_total[5m]))`
   - Alert if < 95%

4. **Cost by Model** (Bar Gauge)
   - Query: `sum by (model) (increase(llm_cost_total{currency="EUR"}[1h]))`

---

##### Dashboard 06 - Conversations (3 panels)

**Purpose**: Conversation metrics, checkpoint performance

**Key Panels**:
1. **Active Conversations** (Stat)
   - Query: `conversation_active_users_total`
   - Thresholds: 100 (yellow), 500 (red)

2. **Checkpoint Save Performance** (Graph)
   - Query: `histogram_quantile(0.99, rate(checkpoint_save_duration_seconds_bucket[5m]))`
   - Recording rule: `checkpoint_save:p99:5m`
   - Alert if p99 > 2s

3. **Checkpoint Size Distribution** (Graph)
   - Query: `histogram_quantile(0.95, rate(checkpoint_size_bytes_bucket[1h]))`

---

##### Dashboard 07 - HITL Tool Approval (14 panels + 8 alerts)

**Purpose**: Human-in-the-Loop quality monitoring

**Key Panels**:
1. **HITL Approval Rate** (Gauge)
   - Query: `sum(rate(hitl_classification_method_total{decision="APPROVE"}[1h])) / sum(rate(hitl_classification_method_total[1h]))`
   - Recording rule: `hitl_approval_rate:1h`

2. **Edit Actions Distribution** (Pie Chart)
   - Query: `sum by (edit_type) (rate(hitl_edit_actions_total[1h]))`
   - Types: `minor_edit`, `moderate_edit`, `full_rewrite`

3. **Rejection Reasons** (Table)
   - Query: `sum by (rejection_type) (rate(hitl_rejection_type_total[1h]))`

**Associated Alert Rules**:
- `HITLClarificationFallbackHigh` (>20%)
- `HITLClarificationFallbackCritical` (>40%)
- `HITLFullRewritesHigh` (>30%)
- `HITLExplicitRejectionsHigh` (>20%)
- `HITLRejectionRateSpike` (>50%)
- `HITLUserResponseTimeSlow` (p95 >5min)
- `HITLQualityDegraded` (multiple indicators)

---

##### Dashboard 08 - OAuth Security (10 panels)

**Purpose**: OAuth 2.1 security monitoring (PKCE, state validation)

**Key Panels**:
1. **OAuth Callback Success Rate** (Gauge)
   - Query: `sum(rate(oauth_callback_total{status="success"}[5m])) / sum(rate(oauth_callback_total[5m]))`
   - Recording rule: `oauth_callback_success_rate:5m`

2. **PKCE Validation Failures** (Stat)
   - Query: `sum(rate(oauth_pkce_validation_total{result="failed"}[5m]))`
   - Alert if > 5/s (possible CSRF attack)

3. **OAuth Callback Latency p95** (Graph)
   - Query: `histogram_quantile(0.95, rate(oauth_callback_duration_seconds_bucket[5m]))`

---

##### Dashboard 09 - Logs & Traces (12 panels)

**Purpose**: Log aggregation, trace visualization, error tracking

**Key Panels**:
1. **Logs by Level** (Graph)
   - LogQL: `sum by (level) (count_over_time({job="lia-api"}[5m]))`

2. **Top 10 Most Frequent Errors** (Table)
   - LogQL: `topk(10, sum(count_over_time({job="lia-api"} | json | level="ERROR" [1h])) by (message))`

3. **Trace Latency Distribution** (Histogram)
   - TraceQL: `{service.name="lia-api"}`

---

##### Dashboard 10 - Redis Rate Limiting (13 panels)

**Purpose**: Redis-based rate limiting monitoring (sliding window algorithm)

**Added**: Phase 2.4 (Session 4-5)

**Key Panels**:
1. **Rate Limit Allows/Denies** (Timeseries)
   - Query: `sum by (connector_type, allowed) (rate(redis_rate_limit_acquire_total[5m]))`
   - Monitor: Allow vs Deny ratio by connector

2. **Rate Limit Check Latency P50/P95/P99** (Timeseries)
   - Query: `histogram_quantile(0.95, sum by (le, connector_type) (rate(redis_rate_limit_check_duration_seconds_bucket[5m])))`
   - Recording rule: `key_prefix:redis_rate_limit_check_duration_ms:p95_rate5m`
   - SLA: P95 < 10ms (Lua script execution)

3. **Blocked Requests (429) - Last Hour** (Stat)
   - Query: `sum(increase(redis_rate_limit_blocked_total[1h]))`
   - Threshold: >100 (yellow), >500 (red)

4. **Redis Connection Pool Utilization** (Gauge)
   - Query: `redis_connection_pool_utilization_ratio`
   - Alert if > 80%

---

##### Dashboard 11 - LangGraph Framework (40+ panels)

**Purpose**: LangGraph framework internals monitoring (graphs, nodes, state, subgraphs, streaming)

**Added**: Phase 2.5 (Session 5)

**Sections**:
1. **Graph Execution** (12 panels):
   - Graph duration P95/P99
   - Graph error rate
   - Concurrent graphs
   - Graph execution rate

2. **Node Transitions** (10 panels):
   - State transitions heatmap
   - Node-to-node latency
   - Conditional edge decisions
   - Node error rate by type

3. **State Management** (8 panels):
   - State size distribution (KB)
   - State update frequency
   - State complexity (nested depth)

4. **SubGraphs** (6 panels):
   - SubGraph duration by agent
   - Nested subgraph depth
   - SubGraph invocation rate

5. **Streaming Events** (6 panels):
   - SSE event distribution by type
   - Event payload size
   - Streaming error rate

**Key Metrics**:
- `langgraph_graph_duration_seconds` (P95 < 5s)
- `langgraph_state_size_bytes` (P95 < 100KB)
- `langgraph_node_transitions_total` (track graph flow)
- `langgraph_subgraph_duration_seconds` (ReAct loop performance)

---

##### Dashboard 12 - Recording Rules Health (13 panels)

**Purpose**: Meta-monitoring of Prometheus recording rules (performance, evaluation time)

**Added**: Phase 2.2 (Session 8)

**Key Panels**:
1. **Recording Rule Evaluation Duration** (Timeseries)
   - Query: `prometheus_rule_evaluation_duration_seconds{rule_group=~".*_optimized"}`
   - Monitor: Evaluation time for each rule group

2. **Recording Rule Failures** (Stat)
   - Query: `sum(rate(prometheus_rule_evaluation_failures_total[1h]))`
   - Alert if > 0 (rules should never fail)

3. **Recording Rules Coverage** (Stat)
   - Total: 31 rules across 8 groups
   - Performance gain: 98% (query time reduction)

4. **Top 10 Slowest Recording Rules** (Table)
   - Query: `topk(10, prometheus_rule_evaluation_duration_seconds)`

**Recording Rule Groups**:
- `oauth_security_optimized` (4 rules)
- `hitl_quality_optimized` (8 rules)
- `redis_rate_limiting_optimized` (3 rules)
- `langgraph_framework_optimized` (3 rules)
- `llm_performance_optimized` (3 rules)
- `slo_tracking` (10+ rules)

---

##### Dashboard 13 - SLO Tracking (15 panels)

**Purpose**: Service Level Objectives tracking (Google SRE)

**Added**: Phase 2.2 (Session 8)

**SLO Categories**:

1. **API Latency SLOs** (5 panels):
   - **SLO Target**: P95 < 500ms
   - **SLO Compliance**: `api:slo:latency_p95_500ms:compliance_ratio`
   - **Error Budget**: 30-day rolling window
   - **Burn Rate**: 1h, 6h, 3d windows

2. **Availability SLOs** (3 panels):
   - **SLO Target**: 99.9% uptime (3 nines)
   - **Current Availability**: `api:slo:availability:ratio_5m`
   - **Error Budget Remaining**: `api:slo:error_budget:remaining_30d`
   - **Fast Burn Alert**: If >10% budget consumed in 1h

3. **Agent Latency SLOs** (3 panels):
   - **SLO Target**: Agent P95 < 3000ms
   - **Current P95/P99**: `agent:latency:p95_5m`, `agent:latency:p99_5m`
   - **Success Rate**: `agent:slo:success_rate:1h` (target 95%)

4. **LLM Provider SLOs** (2 panels):
   - **SLO Target**: 99% availability, P95 < 2000ms
   - **Provider Availability**: `llm:slo:availability:ratio_5m`
   - **Rate Limit Hits**: `llm:rate_limits:hits_per_hour`

5. **Business SLOs** (2 panels):
   - **Abandonment Rate**: < 15% (target)
   - **HITL Approval Rate**: > 80% (target)
   - **Conversation Cost**: Average cost per conversation

**Recording Rules Used**:
All SLO panels use pre-aggregated recording rules from `slo_tracking` group for fast query performance.

---

##### Dashboard 14 - Langfuse LLM Observability (20+ panels)

**Purpose**: Langfuse integration monitoring (prompt versioning, eval scores, traces)

**Added**: Phase 3.1 (Sessions 10-13)

**Sections**:

1. **Trace Ingestion** (5 panels):
   - Trace creation rate
   - Trace ingestion latency P95
   - Failed trace uploads
   - Trace payload size distribution

2. **Prompt Versioning** (6 panels):
   - Active prompt versions by name
   - Prompt performance by version (A/B testing)
   - Prompt rollout status
   - Version change frequency

3. **Evaluation Scores** (5 panels):
   - Score distribution by metric (correctness, helpfulness, toxicity)
   - Average score trends
   - Low-scoring interactions (< 0.5)
   - Evaluation coverage (% of traces scored)

4. **Nested Traces** (4 panels):
   - Trace depth distribution
   - Parent-child relationships
   - Subgraph trace correlation
   - Trace completeness (all spans present)

**Key Metrics**:
- `langfuse_trace_created_total`
- `langfuse_prompt_version_active_total`
- `langfuse_evaluation_score` (histogram)
- `langfuse_trace_upload_duration_seconds`

---

##### Dashboard 15 - Checkpoint Observability (13 panels)

**Purpose**: LangGraph checkpoint persistence layer monitoring

**Added**: Phase 3.3 (Session 15)

**Sections**:

1. **Operations** (4 panels):
   - Save/Load operations rate
   - Operation success rate
   - Operations by status (success/error)
   - Concurrent checkpoint operations

2. **Latency** (3 panels):
   - Save duration P50/P95/P99 by node
   - Load duration P50/P95/P99 (with/without conversation)
   - Alert: P99 save > 2s, P99 load > 1s

3. **Size** (2 panels):
   - Checkpoint size distribution (bytes)
   - P90 size by node (storage optimization)
   - Large checkpoints (>500KB)

4. **Errors** (4 panels):
   - Error rate by type (db_connection, serialization, timeout, permission)
   - Error count breakdown
   - Save failures (critical alert)
   - Load failures

**Key Metrics**:
- `checkpoint_operations_total{operation="save|load", status="success|error"}`
- `checkpoint_errors_total{error_type, operation}`
- `checkpoint_save_duration_seconds` (histogram, buckets: 10ms-1s)
- `checkpoint_load_duration_seconds` (histogram, buckets: 10ms-2s)
- `checkpoint_size_bytes` (histogram, buckets: 100B-1MB)

**Alerts**:
- `CheckpointSaveLatencyHigh`: P95 > 1s (warning)
- `CheckpointSaveLatencyCritical`: P99 > 2s (critical)
- `CheckpointSizeTooBig`: P90 > 500KB (warning)
- `CheckpointSaveFailures`: Error rate > 1% (critical, PagerDuty)

---

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
      path: /var/tempo/traces
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
  metrics_generator_processors:
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
- `http.target`: Full URL path
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

**Location**: `infrastructure/observability/prometheus/alertmanager/`

**Purpose**: Handle alerts from Prometheus, deduplicate, group, and route to notification channels.

For exhaustive documentation, see: [AlertManager README](prometheus/alertmanager/README.md)

#### Alert Rules Summary

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

```
Default route → default-email
│
├─ severity: critical → critical-multi-channel (Email + Slack + PagerDuty)
│
├─ severity: warning → warning-email-slack (Email + Slack)
│
├─ component: llm, severity: critical → llm-budget-critical (Finance + Ops)
│
├─ component: agents → agents-performance (Agents team)
│
├─ component: postgresql → database-team (Database team)
│
├─ component: redis → redis-team (Redis team)
│
└─ component: oauth, severity: critical → security-team (Security + PagerDuty)
```

#### Email Templates

**8 specialized templates** (426 lines total):
1. `email.default.html` - Generic alerts
2. `email.critical.html` - High-priority alerts (red header, action checklist)
3. `email.warning.html` - Warning alerts (orange header)
4. `email.budget.html` - LLM cost budget alerts (budget breakdown chart)
5. `email.agents.html` - Agent SLA violations (runbook emphasis)
6. `email.database.html` - PostgreSQL alerts
7. `email.redis.html` - Redis alerts
8. `email.security.html` - OAuth security incidents (security warning box)

---

## 📈 Metrics Instrumentation

### Metrics Inventory

**Total**: 180+ metrics across 9 categories

For exhaustive metrics inventory with descriptions, see: [METRICS_INVENTORY_ANALYSIS.md](../docs/optim_monitoring/METRICS_INVENTORY_ANALYSIS.md)

#### 1. LLM Agents (35+ metrics)

**File**: `apps/api/src/infrastructure/observability/metrics_agents.py`

**Key Metrics**:
```python
# SSE Streaming Performance
sse_time_to_first_token_seconds = Histogram(
    "sse_time_to_first_token_seconds",
    "Time to first token in SSE streaming",
    ["intention"],
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
)

sse_tokens_generated_total = Counter(
    "sse_tokens_generated_total",
    "Total tokens generated during SSE streaming",
    ["intention", "model"]
)

# Router Performance
router_latency_seconds = Histogram(
    "router_latency_seconds",
    "Router decision latency",
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 2.0, 3.0, 5.0]
)

router_decisions_total = Counter(
    "router_decisions_total",
    "Router decisions by intention and confidence",
    ["intention", "confidence_bucket"]
)

# HITL Tool Approval
hitl_classification_method_total = Counter(
    "hitl_classification_method_total",
    "HITL classification method used",
    ["method", "decision"]
)

hitl_edit_actions_total = Counter(
    "hitl_edit_actions_total",
    "HITL edit actions by type",
    ["edit_type"]  # minor_edit, moderate_edit, full_rewrite
)
```

#### 2. LLM Tokens & Cost (20+ metrics)

**File**: `apps/api/src/infrastructure/observability/metrics_llm.py`

**Key Metrics**:
```python
llm_tokens_consumed_total = Counter(
    "llm_tokens_consumed_total",
    "Total tokens consumed (prompt + completion)",
    ["model", "token_type", "intention"]
)

llm_cost_total = Counter(
    "llm_cost_total",
    "Total LLM API cost",
    ["model", "currency", "intention"]
)

llm_api_calls_total = Counter(
    "llm_api_calls_total",
    "LLM API calls by model and status",
    ["model", "status"]  # success, error
)

llm_api_latency_seconds = Histogram(
    "llm_api_latency_seconds",
    "LLM API call latency",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
)
```

#### 3. HITL Tool Approval (18+ metrics)

**File**: `apps/api/src/infrastructure/observability/metrics_agents.py`

**Key Metrics**:
```python
hitl_classification_method_total = Counter(
    "hitl_classification_method_total",
    "Classification method: llm_classifier or clarification_fallback",
    ["method", "decision"]
)

hitl_user_response_time_seconds = Histogram(
    "hitl_user_response_time_seconds",
    "Time user takes to respond to HITL interrupt",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

hitl_edit_actions_total = Counter(
    "hitl_edit_actions_total",
    "Edit actions on tool proposals",
    ["edit_type"]
)

hitl_rejection_type_total = Counter(
    "hitl_rejection_type_total",
    "Rejection types (explicit vs implicit)",
    ["rejection_type"]
)
```

#### 4. Conversations (15+ metrics)

**File**: `apps/api/src/infrastructure/observability/metrics_conversations.py`

**Key Metrics**:
```python
conversation_created_total = Counter(
    "conversation_created_total",
    "Total conversations created"
)

conversation_active_users_total = Gauge(
    "conversation_active_users_total",
    "Number of users with active conversations"
)

checkpoint_save_duration_seconds = Histogram(
    "checkpoint_save_duration_seconds",
    "Checkpoint save duration",
    ["node_name"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
)

checkpoint_size_bytes = Histogram(
    "checkpoint_size_bytes",
    "Checkpoint size in bytes",
    ["node_name"],
    buckets=[1000, 5000, 10000, 50000, 100000, 500000, 1000000]
)
```

#### 5. OAuth 2.1 Security (12+ metrics)

**File**: `apps/api/src/infrastructure/observability/metrics_oauth.py`

**Key Metrics**:
```python
oauth_callback_total = Counter(
    "oauth_callback_total",
    "OAuth callbacks received",
    ["provider", "status"]
)

oauth_pkce_validation_total = Counter(
    "oauth_pkce_validation_total",
    "PKCE validation results",
    ["provider", "result"]
)

oauth_state_validation_total = Counter(
    "oauth_state_validation_total",
    "State token validation results (CSRF protection)",
    ["provider", "result"]
)

oauth_callback_duration_seconds = Histogram(
    "oauth_callback_duration_seconds",
    "OAuth callback processing duration",
    ["provider"],
    buckets=[0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0]
)
```

#### 6. HTTP/API (10+ metrics)

**File**: `apps/api/src/infrastructure/observability/metrics.py`

**Key Metrics**:
```python
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
```

#### 7. Infrastructure (25+ metrics)

**Exporters**:
- **Node Exporter** (node metrics): CPU, memory, disk, network
- **cAdvisor** (container metrics): Container CPU, memory, network
- **PostgreSQL Exporter**: Database connections, queries, replication
- **Redis Exporter**: Memory, connections, commands

#### 8. Business (15+ metrics)

**File**: `apps/api/src/infrastructure/observability/metrics.py`

**Key Metrics**:
```python
lia_total_users = Gauge(
    "lia_total_users",
    "Total registered users"
)

lia_active_users = Gauge(
    "lia_active_users",
    "Active users in last 24h"
)

lia_total_connectors = Gauge(
    "lia_total_connectors",
    "Total connectors configured"
)

lia_connectors_by_type = Gauge(
    "lia_connectors_by_type",
    "Connectors by type",
    ["type"]
)
```

---

## 🔔 Alerting

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

**Total**: 65+ recording rules

### Recording Rule Naming Convention

```
<metric_name>:<aggregation>:<window>

Examples:
- http_requests:rate:5m          # HTTP request rate (5min window)
- sse_ttft:p95:5m                # TTFT p95 (5min window)
- llm_cost_per_request:1h        # Cost per request (1h window)
```

### Key Recording Rules

#### LLM Costs (5 rules)

```yaml
# LLM cost per request (hourly average)
- record: llm_cost_per_request:1h
  expr: |
    sum(rate(llm_cost_total{currency="USD"}[1h]))
    /
    sum(rate(llm_api_calls_total[1h]))

# Tokens per request
- record: llm_tokens_per_request:1h
  expr: |
    sum(rate(llm_tokens_consumed_total[1h]))
    /
    sum(rate(llm_api_calls_total[1h]))

# Cost by model (1h window)
- record: llm_cost_by_model:1h
  expr: |
    sum by (model) (rate(llm_cost_total{currency="USD"}[1h]))
```

#### Agent Performance (8 rules)

```yaml
# TTFT percentiles (5min window)
- record: sse_ttft:p50:5m
  expr: |
    histogram_quantile(0.5, sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (intention, le))

- record: sse_ttft:p95:5m
  expr: |
    histogram_quantile(0.95, sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (intention, le))

# Tokens per second by intention
- record: sse_tokens_per_second:5m
  expr: |
    sum by (intention) (rate(sse_tokens_generated_total[5m]))
    /
    sum by (intention) (rate(sse_streaming_duration_seconds_count[5m]))

# Router latency p95
- record: router_latency:p95:5m
  expr: |
    histogram_quantile(0.95, sum(rate(router_latency_seconds_bucket[5m])) by (le))
```

#### HITL Quality (6 rules)

```yaml
# HITL approval rate (1h window)
- record: hitl_approval_rate:1h
  expr: |
    sum(rate(hitl_classification_method_total{decision="APPROVE"}[1h]))
    /
    sum(rate(hitl_classification_method_total[1h]))

# HITL edit rate
- record: hitl_edit_rate:1h
  expr: |
    sum(rate(hitl_edit_actions_total[1h]))
    /
    sum(rate(hitl_classification_method_total[1h]))

# Clarification fallback rate
- record: hitl_clarification_fallback_rate:1h
  expr: |
    sum(rate(hitl_clarification_fallback_total[1h]))
    /
    sum(rate(hitl_classification_method_total[1h]))
```

---

## 💾 Data Retention

### Retention Policies

| Component | Retention | Configurable | Location |
|-----------|-----------|--------------|----------|
| **Prometheus** | 15 days | Yes (`--storage.tsdb.retention.time`) | `prometheus.yml` |
| **Loki** | 7 days | Yes (`retention_period`) | `loki-config.yml` |
| **Tempo** | 7 days | Yes (`block_retention`) | `tempo.yml` |
| **Grafana** | N/A (queries only) | N/A | N/A |
| **AlertManager** | N/A (stateful, not time-series) | N/A | Silences stored in memory |

### Disk Space Estimation

**Total**: ~10GB for full stack (15 days Prometheus, 7 days logs/traces)

| Component | Daily Usage | 15 Days | 7 Days |
|-----------|-------------|---------|--------|
| Prometheus | ~500MB | ~7.5GB | ~3.5GB |
| Loki | ~50MB | ~750MB | ~350MB |
| Tempo | ~100MB | ~1.5GB | ~700MB |
| Grafana | ~10MB | ~150MB | ~70MB |
| **Total** | ~660MB | **~10GB** | **~4.6GB** |

### Retention Configuration Changes

#### Prometheus

Edit `docker-compose.yml`:

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
sse_ttft:p95:5m
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
2. ✅ Configure Loki logging driver in `docker-compose.yml`:
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
docker logs lia-alertmanager | grep -i smtp
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

- [Grafana Dashboards README](grafana/dashboards/README.md) - Exhaustive panel documentation (2330 lines)
- [AlertManager README](prometheus/alertmanager/README.md) - Alert rules & routing (2494 lines)
- [Metrics Inventory Analysis](../docs/optim_monitoring/METRICS_INVENTORY_ANALYSIS.md) - Complete metrics catalog (1000+ lines)

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
