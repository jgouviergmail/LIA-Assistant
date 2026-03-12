# AlertManager Configuration - LIA

**Version**: 2.0 (2025-11-22)
**Status**: Production-Ready
**Alert Rules**: 57 alerts across 9 groups
**Templates**: 8 specialized email templates
**Receivers**: 8 receivers with multi-channel routing

Production-ready AlertManager configuration for LIA observability infrastructure with intelligent routing, inhibition rules, and specialized notification templates.

---

## 📋 Table of Contents

1. [Overview](#-overview)
2. [Architecture](#-architecture)
3. [Quick Start](#-quick-start)
4. [Alert Rules Inventory](#-alert-rules-inventory)
5. [Routing Configuration](#-routing-configuration)
6. [Inhibition Rules](#-inhibition-rules)
7. [Receivers & Templates](#-receivers--templates)
8. [Environment Configuration](#-environment-configuration)
9. [Testing & Validation](#-testing--validation)
10. [Silencing Alerts](#-silencing-alerts)
11. [Monitoring AlertManager](#-monitoring-alertmanager)
12. [Security Best Practices](#-security-best-practices)
13. [Troubleshooting](#-troubleshooting)
14. [References](#-references)

---

## 📊 Overview

### What is AlertManager?

AlertManager handles alerts sent by Prometheus server. It:
- **Deduplicates** identical alerts from multiple sources
- **Groups** related alerts to reduce notification spam
- **Routes** alerts to appropriate teams/channels based on labels
- **Inhibits** redundant alerts using inhibition rules
- **Silences** alerts during maintenance windows
- **Sends** multi-channel notifications (Email, Slack, PagerDuty)

### Alert Statistics

| Metric | Count | Description |
|--------|-------|-------------|
| **Total Alert Rules** | 57 | Active alert rules across all groups |
| **Alert Groups** | 9 | Logical groupings (HITL, Agents, Redis, etc.) |
| **Severity Levels** | 3 | critical, warning, info |
| **Email Templates** | 8 | Specialized templates per component |
| **Receivers** | 8 | Email, Slack, PagerDuty combinations |
| **Inhibition Rules** | 5 | Prevent notification spam |
| **Routing Rules** | 11 | Intelligent alert routing |

### Alert Groups Breakdown

| Group | Alerts | Purpose | Interval |
|-------|--------|---------|----------|
| `hitl_quality` | 10 | HITL classifier, edits, rejections quality | 30s |
| `agents_langgraph_alerts` | 5 | Agent SLA violations (TTFT, tokens/s, router) | 30s |
| `conversations` | 6 | Checkpoint performance, conversation metrics | 30s |
| `tokens_and_cost` | 8 | LLM API failures, cost budgets, token consumption | 1m |
| `oauth_alerts` | 6 | OAuth security, PKCE validation, callback performance | 30s |
| `redis_rate_limiting_alerts` | 9 | Rate limiting hit rates, latency, errors | 30s |
| `redis_alerts` | 3 | Redis uptime, memory, connections | 30s |
| `database_alerts` | 4 | PostgreSQL connections, slow queries | 30s |
| `application_alerts` | 5 | HTTP error rates, latency, service uptime | 30s |
| `infrastructure_alerts` | 6 | Disk, CPU, memory, containers | 30s |

**Total**: 57 alerts

---

## 🏗️ Architecture

### AlertManager Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         Prometheus                               │
│  (Evaluates alert rules every 30s-1m and sends to AlertManager) │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AlertManager                               │
│                                                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐           │
│  │ Deduplication│──▶│   Grouping  │──▶│  Inhibition │           │
│  └─────────────┘   └─────────────┘   └──────┬──────┘           │
│                                               │                   │
│                                               ▼                   │
│                                    ┌─────────────────┐           │
│                                    │     Routing     │           │
│                                    └────────┬────────┘           │
│                                             │                     │
│          ┌──────────────┬──────────────────┼──────────────┐     │
│          ▼              ▼                   ▼              ▼     │
│    ┌─────────┐   ┌──────────┐      ┌──────────┐   ┌──────────┐│
│    │ Critical│   │ Warning  │      │LLM Budget│   │ Security ││
│    │Receiver │   │ Receiver │      │ Receiver │   │ Receiver ││
│    └────┬────┘   └────┬─────┘      └────┬─────┘   └────┬─────┘│
└─────────┼─────────────┼──────────────────┼──────────────┼──────┘
          │             │                  │              │
     ┌────┴───┬────┬───┴───┐         ┌────┴────┐    ┌────┴────┐
     ▼        ▼    ▼       ▼         ▼         ▼    ▼         ▼
  Email    Slack  Email  Slack    Email     Slack Email   PagerDuty
 Critical Critical Warn  Warn    Finance    Budget Security  Security
```

### Alert Flow

1. **Prometheus Evaluation**: Alert rules evaluated every 30s-1m
2. **Firing Condition**: If expression is true for `for` duration, alert fires
3. **AlertManager Receives**: Prometheus sends alert to AlertManager
4. **Deduplication**: Identical alerts from multiple sources merged
5. **Grouping**: Alerts grouped by `group_by` labels (reduces spam)
6. **Inhibition**: Redundant alerts suppressed (e.g., service down inhibits high latency)
7. **Routing**: Alerts routed to receivers based on label matchers
8. **Notification**: Multi-channel notifications sent (Email, Slack, PagerDuty)
9. **Repeat**: Alerts re-sent if still firing after `repeat_interval`

### File Structure

```
alertmanager/
├── alertmanager.yml          # Main configuration (270 lines)
│   ├── global:              # SMTP configuration
│   ├── templates:           # Template file paths
│   ├── route:               # Routing tree (11 routes)
│   ├── inhibit_rules:       # 5 inhibition rules
│   └── receivers:           # 8 receivers
│
├── templates/
│   └── email.tmpl           # 426 lines - 8 email templates
│       ├── email.default.html      (lines 1-60)
│       ├── email.critical.html     (lines 62-131)
│       ├── email.warning.html      (lines 133-186)
│       ├── email.budget.html       (lines 188-250)
│       ├── email.agents.html       (lines 252-307)
│       ├── email.database.html     (lines 309-344)
│       ├── email.redis.html        (lines 346-381)
│       └── email.security.html     (lines 383-425)
│
└── README.md                # This file
```

---

## 🚀 Quick Start

### Prerequisites

- Prometheus installed and running
- SMTP server access (Gmail, SendGrid, etc.)
- Redis running (for state storage)

### 1. Configure Environment Variables

Copy the example environment file:

```bash
cd apps/api
cp .env.alerting.example .env.alerting
```

Edit `.env.alerting` with your configuration:

**Required Variables** (SMTP):
```bash
ALERTMANAGER_SMTP_FROM="alerts@lia.com"
ALERTMANAGER_SMTP_SMARTHOST="smtp.gmail.com:587"
ALERTMANAGER_SMTP_AUTH_USER="your-email@gmail.com"
ALERTMANAGER_SMTP_AUTH_PASSWORD="your-app-password"
ALERTMANAGER_EMAIL_TO_CRITICAL="ops-critical@lia.com"
ALERTMANAGER_EMAIL_TO_WARNING="ops@lia.com"
```

**Optional Variables** (Multi-Channel):
```bash
# Slack integration
ALERTMANAGER_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# PagerDuty integration (for critical alerts)
ALERTMANAGER_PAGERDUTY_SERVICE_KEY="your-pagerduty-integration-key"
```

**Gmail App Password Setup**:
1. Enable 2FA on your Google account
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use the 16-character app password (not your regular password)

### 2. Docker Compose Deployment

Add AlertManager to your `docker-compose.yml`:

```yaml
version: '3.8'

services:
  alertmanager:
    image: prom/alertmanager:v0.27.0  # Latest stable (2025)
    container_name: lia-alertmanager
    restart: unless-stopped

    # Load environment variables
    env_file:
      - ./apps/api/.env.alerting

    # Mount configuration and templates
    volumes:
      - ./infrastructure/observability/prometheus/alertmanager:/etc/alertmanager
      - alertmanager-data:/alertmanager  # Persistent storage for silences

    # AlertManager arguments
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
      - '--web.external-url=http://localhost:9093'
      - '--cluster.listen-address='  # Disable clustering for single instance

    ports:
      - "9093:9093"

    networks:
      - monitoring

    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9093/-/healthy"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  prometheus:
    image: prom/prometheus:v2.50.0
    # ... (existing prometheus config)
    depends_on:
      - alertmanager

volumes:
  alertmanager-data:
    driver: local

networks:
  monitoring:
    driver: bridge
```

Start AlertManager:

```bash
docker-compose up -d alertmanager
```

### 3. Configure Prometheus

Update `prometheus.yml` to send alerts to AlertManager:

```yaml
# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 'alertmanager:9093'  # Docker Compose service name
            # - 'localhost:9093'   # Local development

# Load alert rules
rule_files:
  - '/etc/prometheus/alerts.yml'         # Infrastructure & application alerts
  - '/etc/prometheus/alert_rules.yml'   # HITL quality alerts
```

### 4. Verify Configuration

```bash
# 1. Check AlertManager is healthy
curl http://localhost:9093/-/healthy
# Expected: Healthy

# 2. View AlertManager configuration
curl http://localhost:9093/api/v1/status | jq

# 3. Check if Prometheus is connected
curl http://localhost:9093/api/v1/alerts | jq '.data.alerts | length'
# Expected: 0 (if no alerts firing)

# 4. View AlertManager logs
docker logs lia-alertmanager --tail 50

# 5. Reload configuration (without restart)
curl -X POST http://localhost:9093/-/reload
```

### 5. Send Test Alert

Trigger a test alert to verify end-to-end flow:

```bash
# Send test alert via AlertManager API
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "component": "test"
    },
    "annotations": {
      "summary": "This is a test alert",
      "description": "Testing AlertManager email configuration"
    },
    "startsAt": "2025-11-22T10:00:00Z",
    "endsAt": "2025-11-22T10:30:00Z"
  }
]'
```

**Expected Result**:
- Email received at `ALERTMANAGER_EMAIL_TO_WARNING` address
- Slack message in `#alerts-warning` channel (if configured)
- Alert visible in AlertManager UI: http://localhost:9093

---

## 📊 Alert Rules Inventory

This section documents all 57 alert rules configured across 9 groups.

### Group 1: HITL Quality (10 alerts)

**Purpose**: Monitor Human-in-the-Loop system quality (classifier, edits, rejections)
**Interval**: 30s
**Dashboard**: [07 - HITL Tool Approval](http://grafana:3000/d/hitl/07-hitl-tool-approval)

#### 1.1 HITLClarificationFallbackHigh

**Severity**: warning
**Condition**: Clarification fallback rate > 20% for 10m

```promql
(
  rate(hitl_clarification_fallback_total[5m])
  /
  rate(hitl_classification_method_total[5m])
) > 0.2
```

**Meaning**: HITL classifier unable to make confident decisions in >20% of cases.

**Actions**:
1. Review recent AMBIGUOUS classifications in logs
2. Check if prompt needs tuning
3. Consider retraining classifier with more examples

**Team**: ml
**Channels**: Email + Slack

---

#### 1.2 HITLClarificationFallbackCritical

**Severity**: critical
**Condition**: Clarification fallback rate > 40% for 5m

```promql
(
  rate(hitl_clarification_fallback_total[5m])
  /
  rate(hitl_classification_method_total[5m])
) > 0.4
```

**Meaning**: HITL classifier severely degraded, user experience significantly impacted.

**IMMEDIATE ACTIONS**:
1. Check LLM provider status (OpenAI/Anthropic)
2. Review recent prompt changes
3. Consider rollback if recent deployment
4. Enable fallback to rule-based classification

**Team**: ml
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 1.3 HITLFullRewritesHigh

**Severity**: warning
**Condition**: Full rewrites > 30% of edits for 30m

```promql
(
  sum(rate(hitl_edit_actions_total{edit_type="full_rewrite"}[1h]))
  /
  sum(rate(hitl_edit_actions_total[1h]))
) > 0.3
```

**Meaning**: Users rewriting agent proposals completely indicates proposals are off-target.

**Actions**:
1. Review recent full_rewrite examples in logs
2. Analyze which agents/tools have highest rewrite rate
3. Consider A/B testing improved prompts

**Team**: product
**Channels**: Email + Slack

---

#### 1.4 HITLEditRateIncreasing

**Severity**: info
**Condition**: Edit rate > 40% of HITL interactions for 1h

```promql
(
  rate(hitl_edit_actions_total[1h])
  /
  rate(hitl_classification_method_total[1h])
) > 0.4
```

**Meaning**: High edit rate may indicate declining proposal quality.

**Team**: product
**Channels**: Email + Slack

---

#### 1.5 HITLExplicitRejectionsHigh

**Severity**: warning
**Condition**: Explicit rejections > 20% for 30m

```promql
(
  sum(rate(hitl_rejection_type_total{rejection_type="explicit_no"}[1h]))
  /
  sum(rate(hitl_rejection_type_total[1h]))
) > 0.2
```

**Meaning**: Users explicitly rejecting proposals with "no/annule/stop" indicates unwanted actions.

**Actions**:
1. Review explicit rejection examples by agent type
2. Check if specific tools have high rejection rates
3. Consider making proposals more conservative

**Team**: product
**Channels**: Email + Slack

---

#### 1.6 HITLRejectionRateSpike

**Severity**: critical
**Condition**: Rejection rate > 50% for 10m

```promql
(
  rate(hitl_rejection_type_total[5m])
  /
  rate(hitl_classification_method_total[5m])
) > 0.5
```

**Meaning**: Sudden spike in rejections, possible bad deployment or LLM model change.

**IMMEDIATE ACTIONS**:
1. Check recent deployments (last 2h)
2. Review logs for error patterns
3. Consider rollback if correlated with deployment

**Team**: product
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 1.7 HITLUserResponseTimeSlow

**Severity**: warning
**Condition**: User response time p95 > 300s for 15m

```promql
histogram_quantile(0.95,
  sum by (le) (rate(hitl_user_response_time_seconds_bucket[5m]))
) > 300
```

**Meaning**: Users taking >5min to respond indicates UX friction or unclear prompts.

**Actions**:
- Are HITL questions clear and concise?
- Is interrupt timing appropriate (not spammy)?
- Are users abandoning after HITL prompts?

**Team**: product
**Channels**: Email + Slack

---

#### 1.8 HITLQualityDegraded

**Severity**: warning
**Condition**: Clarification fallback >15% AND explicit rejection >15% for 1h

```promql
(
  (rate(hitl_clarification_fallback_total[1h]) / rate(hitl_classification_method_total[1h])) > 0.15
  and
  (sum(rate(hitl_rejection_type_total{rejection_type="explicit_no"}[1h])) / sum(rate(hitl_rejection_type_total[1h]))) > 0.15
)
```

**Meaning**: Multiple HITL quality indicators degraded simultaneously (systemic issue).

**Actions**:
1. Review recent changes to agents or classifier
2. Analyze user feedback patterns
3. Consider A/B test of previous agent version

**Team**: product
**Channels**: Email + Slack

---

#### 1.9 HITLCombinedMetrics (Placeholder)

**Note**: Alert 1.9 and 1.10 slots reserved for future HITL quality metrics.

---

### Group 2: Agents LangGraph (5 alerts)

**Purpose**: Monitor agent SLA violations (TTFT, tokens/s, router latency)
**Interval**: 30s
**Dashboard**: [04 - Agents LangGraph](http://grafana:3000/d/agents-langgraph)

#### 2.1 AgentsTTFTViolation

**Severity**: warning
**SLA**: Time to First Token < 1000ms
**Condition**: TTFT p95 > 5000ms for 5m

```promql
histogram_quantile(0.95,
  sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le, intention)
) * 1000 > 5000
```

**Meaning**: Users experiencing perceptible latency (SLA violated).

**Runbook**:
1. Vérifier la latence router (< 500ms)
2. Vérifier l'API OpenAI (latency network)
3. Vérifier context size (trop de messages history)
4. Consulter dashboard 'LangGraph Agents Observability'

**Team**: agents
**Channels**: Email + Slack via `agents-performance` receiver

---

#### 2.2 AgentsTokensPerSecondLow

**Severity**: warning
**SLA**: Tokens/sec > 20
**Condition**: Token generation rate < 5 tokens/s for 5m

```promql
(
  sum(rate(sse_tokens_generated_total[5m])) by (intention)
  /
  sum(rate(sse_streaming_duration_seconds_sum[5m])) by (intention)
) < 5
```

**Meaning**: Low throughput degrades user experience.

**Runbook**:
1. Vérifier model selection (gpt-4-mini > gpt-4.1-mini)
2. Optimiser RESPONSE_LLM_TEMPERATURE (< 0.7 = plus rapide)
3. Réduire RESPONSE_LLM_MAX_TOKENS
4. Vérifier streaming buffer delays

**Team**: agents
**Channels**: Email + Slack

---

#### 2.3 AgentsRouterLatencyHigh

**Severity**: critical
**SLA**: Router latency < 500ms
**Condition**: Router p95 latency > 3000ms for 5m

```promql
histogram_quantile(0.95,
  sum(rate(router_latency_seconds_bucket[5m])) by (le)
) * 1000 > 3000
```

**Meaning**: Router blocking all users (critical bottleneck).

**Runbook**:
1. Vérifier ROUTER_LLM_TEMPERATURE (doit être ≤ 0.2)
2. Vérifier ROUTER_LLM_MAX_TOKENS (500 suffisant)
3. Vérifier router_fallback_total (échecs fréquents?)
4. Vérifier OpenAI API status

**Team**: agents
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 2.4 AgentsStreamingErrorRateHigh

**Severity**: critical
**SLA**: Streaming error rate < 5%
**Condition**: Error rate > 25% for 3m

```promql
(
  sum(rate(sse_streaming_errors_total[5m]))
  /
  sum(rate(sse_streaming_duration_seconds_count[5m]))
) * 100 > 25
```

**Meaning**: Major user impact, streaming failures widespread.

**Runbook**:
1. Vérifier logs Loki: `{job="api", level="error", logger_name=~".*agents.*"}`
2. Consulter 'Top 10 Most Frequent Errors' dans dashboard Logs & Traces
3. Vérifier `graph_exceptions_total` par node_name
4. Vérifier `llm_api_calls_total{status="error"}`

**Team**: agents
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 2.5 AgentsRouterLowConfidenceHigh

**Severity**: warning
**SLA**: Router confidence > 0.6
**Condition**: Low confidence decisions > 40% for 10m

```promql
(
  sum(rate(router_decisions_total{confidence_bucket="low"}[10m]))
  /
  sum(rate(router_decisions_total[10m]))
) * 100 > 40
```

**Meaning**: Router quality degraded, unable to make confident decisions.

**Runbook**:
1. Analyser router_debug logs (reasoning field)
2. Vérifier router prompt (manque contexte?)
3. Consulter router_fallback_total (fallbacks fréquents?)
4. Vérifier distribution intentions (nouveaux cas non couverts?)

**Team**: agents
**Channels**: Email + Slack

---

### Group 3: Conversations (6 alerts)

**Purpose**: Monitor checkpoint save/load performance and conversation metrics
**Interval**: 30s
**Dashboard**: [06 - Conversations](http://grafana:3000/d/conversations)

#### 3.1 CheckpointSaveSlowCritical

**Severity**: critical
**Condition**: Checkpoint save p99 > 10s for 5m

```promql
histogram_quantile(0.99, sum(rate(checkpoint_save_duration_seconds_bucket[5m])) by (le, node_name)) > 10.0
```

**Meaning**: Database performance issue or large payloads causing critical latency.

**Team**: conversations
**Channels**: Email + Slack

---

#### 3.2 CheckpointSaveSlowWarning

**Severity**: warning
**Condition**: Checkpoint save p99 > 5s for 10m

```promql
histogram_quantile(0.99, sum(rate(checkpoint_save_duration_seconds_bucket[5m])) by (le, node_name)) > 5.0
```

**Meaning**: Monitor for increasing trend.

**Team**: conversations
**Channels**: Email + Slack

---

#### 3.3 HighConversationResetRate

**Severity**: warning
**Condition**: Conversation resets > 10/s for 10m

```promql
sum(rate(conversation_resets_total[5m])) > 10.0
```

**Meaning**: Possible UX issue or feature misuse.

**Team**: conversations
**Channels**: Email + Slack

---

#### 3.4 CheckpointSizeGrowing

**Severity**: info
**Condition**: Checkpoint size p95 > 200KB for 30m

```promql
histogram_quantile(0.95, sum(rate(checkpoint_size_bytes_bucket[1h])) by (le, node_name)) > 200000
```

**Meaning**: Monitor for memory/storage impact.

**Team**: conversations
**Channels**: Email + Slack

---

#### 3.5 NoActiveConversations

**Severity**: critical
**Condition**: Zero active users for 15m

```promql
conversation_active_users_total == 0
```

**Meaning**: Possible system outage or data collection issue.

**Team**: conversations
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 3.6 ConversationCreationStalled

**Severity**: warning
**Condition**: No new conversations created in 10m despite active users

```promql
rate(conversation_created_total[10m]) == 0 and conversation_active_users_total > 1
```

**Meaning**: Check database connectivity.

**Team**: conversations
**Channels**: Email + Slack

---

### Group 4: Tokens & Cost (8 alerts)

**Purpose**: Monitor LLM API failures, cost budgets, token consumption
**Interval**: 1m
**Dashboard**: [05 - LLM Tokens & Cost](http://grafana:3000/d/llm-tokens-cost)

#### 4.1 LLMAPIFailureRateHigh

**Severity**: critical
**Condition**: LLM API error rate > 30% for 5m

```promql
sum(rate(llm_api_calls_total{status="error"}[5m]))
/
sum(rate(llm_api_calls_total[5m])) > 0.30
```

**Meaning**: Check OpenAI/Anthropic status page.

**Team**: llm
**Channels**: Email + Slack

---

#### 4.2 LLMAPISuccessRateLow

**Severity**: warning
**Condition**: LLM API success rate < 70% for 10m

```promql
sum(rate(llm_api_calls_total{status="success"}[5m]))
/
sum(rate(llm_api_calls_total[5m])) < 0.70
```

**Team**: llm
**Channels**: Email + Slack

---

#### 4.3 DailyCostBudgetExceeded

**Severity**: critical
**Condition**: Daily cost > 5€ for 1m

```promql
sum(increase(llm_cost_total{currency="EUR"}[24h])) > 5
```

**Meaning**: Daily budget exceeded, review token usage.

**Team**: cost
**Receiver**: `llm-budget-critical` (Finance team + Ops team)
**Channels**: Email + Slack (special budget template)

---

#### 4.4 HourlyCostTrendingHigh

**Severity**: warning
**Condition**: Hourly cost > 1€ for 30m

```promql
sum(increase(llm_cost_total{currency="EUR"}[1h])) > 1
```

**Team**: cost
**Channels**: Email + Slack

---

#### 4.5 LLMAPILatencyHigh

**Severity**: warning
**Condition**: LLM API p99 latency > 30s for 10m

```promql
histogram_quantile(0.99, sum(rate(llm_api_latency_seconds_bucket[5m])) by (le, model)) > 30
```

**Team**: llm
**Channels**: Email + Slack

---

#### 4.6 HighTokenConsumptionRate

**Severity**: info
**Condition**: Token consumption > 10000 tokens/s for 15m

```promql
sum(rate(llm_tokens_consumed_total[5m])) > 10000
```

**Team**: tokens
**Channels**: Email + Slack

---

#### 4.7 ModelCostBudgetExceeded

**Severity**: critical
**Condition**: Per-model daily cost > 3€ for 1m

```promql
sum by (model) (increase(llm_cost_total{currency="EUR"}[24h])) > 3
```

**Team**: cost
**Receiver**: `llm-budget-critical`
**Channels**: Email + Slack

---

#### 4.8 HighOutputTokenRatio

**Severity**: warning
**Condition**: Output/input token ratio > 20 for 30m

```promql
sum(rate(llm_tokens_consumed_total{token_type="completion_tokens"}[10m]))
/
sum(rate(llm_tokens_consumed_total{token_type="prompt_tokens"}[10m])) > 20
```

**Meaning**: Review prompt efficiency and response length.

**Team**: tokens
**Channels**: Email + Slack

---

### Group 5: OAuth Alerts (6 alerts)

**Purpose**: OAuth 2.1 security monitoring (PKCE, state validation, callback performance)
**Interval**: 30s
**Dashboard**: [08 - OAuth Security](http://grafana:3000/d/oauth-security)

#### 5.1 HighOAuthFailureRate

**Severity**: warning
**Condition**: OAuth callback failure rate > 50% for 5m

```promql
(
  sum(rate(oauth_callback_total{status="failed"}[5m])) by (provider)
  /
  sum(rate(oauth_callback_total[5m])) by (provider)
) * 100 > 50
```

**Meaning**: Possible attack or configuration issue.

**Team**: auth
**Security**: Yes
**Channels**: Email + Slack

---

#### 5.2 PKCEValidationFailures

**Severity**: critical
**Condition**: PKCE validation failures > 5/s for 2m

```promql
rate(oauth_pkce_validation_total{result="failed"}[5m]) > 5.0
```

**Meaning**: Possible CSRF attack or Redis cache issue.

**Team**: auth
**Security**: Yes
**PagerDuty**: Yes
**Receiver**: `security-team`
**Channels**: Email + PagerDuty

---

#### 5.3 StateTokenValidationFailures

**Severity**: critical
**Condition**: State token validation failures > 5/s for 2m

```promql
rate(oauth_state_validation_total{result="failed"}[5m]) > 5.0
```

**Meaning**: Possible CSRF attack or synchronization issue.

**Team**: auth
**Security**: Yes
**PagerDuty**: Yes
**Receiver**: `security-team`
**Channels**: Email + PagerDuty

---

#### 5.4 SlowOAuthCallback

**Severity**: warning
**Condition**: OAuth callback p95 > 30s for 5m

```promql
histogram_quantile(0.95,
  sum(rate(oauth_callback_duration_seconds_bucket[5m])) by (le, provider)
) > 30
```

**Meaning**: Check network latency to Google API.

**Team**: auth
**Channels**: Email + Slack

---

#### 5.5 OAuthProviderErrors

**Severity**: warning
**Condition**: OAuth provider errors > 10/s for 3m

```promql
rate(oauth_provider_errors_total[5m]) > 10.0
```

**Meaning**: Check Google API quotas.

**Team**: auth
**Channels**: Email + Slack

---

#### 5.6 OAuthCallbackSpike

**Severity**: warning
**Condition**: OAuth callbacks > 100/s for 2m

```promql
rate(oauth_callback_total[1m]) > 100
```

**Meaning**: Possible attack or bot.

**Team**: auth
**Security**: Yes
**Channels**: Email + Slack

---

### Group 6: Redis Rate Limiting (9 alerts)

**Purpose**: Monitor Redis-based distributed rate limiting
**Interval**: 30s
**Dashboard**: [02 - Infrastructure Resources](http://grafana:3000/d/infra-resources)

#### 6.1 RedisRateLimitHighHitRate

**Severity**: critical
**Condition**: Rate limit hit rate > 50% for 10m

```promql
(
  sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix)
  /
  (sum(rate(redis_rate_limit_allows_total[5m])) by (key_prefix) + sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix))
) * 100 > 50
```

**Meaning**: Users heavily impacted, >50% requests rejected.

**Team**: redis
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 6.2 RedisRateLimitModerateHitRate

**Severity**: warning
**Condition**: Rate limit hit rate > 30% for 15m

```promql
(
  sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix)
  /
  (sum(rate(redis_rate_limit_allows_total[5m])) by (key_prefix) + sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix))
) * 100 > 30
```

**Team**: redis
**Channels**: Email + Slack

---

#### 6.3 RedisRateLimitCheckLatencyHigh

**Severity**: critical
**Condition**: Rate limit check p95 > 50ms for 5m

```promql
1000 * histogram_quantile(0.95,
  sum(rate(redis_rate_limit_check_duration_seconds_bucket[5m])) by (le, key_prefix)
) > 50
```

**Meaning**: Impact global performance.

**Team**: redis
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 6.4 RedisRateLimitCheckLatencyDegraded

**Severity**: warning
**Condition**: Rate limit check p95 > 10ms for 10m

```promql
1000 * histogram_quantile(0.95,
  sum(rate(redis_rate_limit_check_duration_seconds_bucket[5m])) by (le, key_prefix)
) > 10
```

**Team**: redis
**Channels**: Email + Slack

---

#### 6.5 RedisConnectionPoolExhaustion

**Severity**: critical
**Condition**: Connection pool utilization > 95% for 5m

```promql
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current)) > 95
```

**Meaning**: Connections blocked.

**Team**: redis
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 6.6 RedisConnectionPoolHighUtilization

**Severity**: warning
**Condition**: Connection pool utilization > 80% for 10m

```promql
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current)) > 80
```

**Team**: redis
**Channels**: Email + Slack

---

#### 6.7 RedisRateLimitErrorsHigh

**Severity**: critical
**Condition**: Rate limit errors > 10/s for 3m

```promql
sum(rate(redis_rate_limit_errors_total[5m])) by (error_type) > 10
```

**Meaning**: Service degraded.

**Team**: redis
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

#### 6.8 RedisRateLimitErrorsDetected

**Severity**: warning
**Condition**: Rate limit errors > 1/s for 10m

```promql
sum(rate(redis_rate_limit_errors_total[5m])) by (error_type) > 1
```

**Team**: redis
**Channels**: Email + Slack

---

#### 6.9 RedisLuaScriptFailureRateHigh

**Severity**: critical
**Condition**: Lua script failure rate > 5% for 5m

```promql
(
  sum(rate(redis_lua_script_executions_total{status="error"}[5m]))
  /
  sum(rate(redis_lua_script_executions_total[5m]))
) * 100 > 5
```

**Meaning**: Rate limiting compromised.

**Team**: redis
**PagerDuty**: Yes
**Channels**: Email + Slack + PagerDuty

---

### Group 7: Redis Alerts (3 alerts)

**Purpose**: Redis uptime, memory, connections
**Interval**: 30s

#### 7.1 RedisDown

**Severity**: critical
**Condition**: Redis down for 1m

```promql
up{job="redis"} == 0
```

**Team**: redis
**Receiver**: `redis-team`
**Channels**: Email

---

#### 7.2 RedisMemoryHigh

**Severity**: warning
**Condition**: Redis memory > 95% for 5m

```promql
(redis_memory_used_bytes / redis_memory_max_bytes) * 100 > 95
```

**Team**: redis
**Receiver**: `redis-team`
**Channels**: Email

---

#### 7.3 RedisConnectionsHigh

**Severity**: warning
**Condition**: Redis connections > 500 for 5m

```promql
redis_connected_clients > 500
```

**Team**: redis
**Receiver**: `redis-team`
**Channels**: Email

---

### Group 8: Database Alerts (4 alerts)

**Purpose**: PostgreSQL connections, slow queries
**Interval**: 30s

#### 8.1 HighDatabaseConnections

**Severity**: warning
**Condition**: DB connections > 95% for 5m

```promql
(
  pg_stat_database_numbackends{datname="lia"}
  /
  pg_settings_max_connections
) * 100 > 95
```

**Team**: postgresql
**Receiver**: `database-team`
**Channels**: Email

---

#### 8.2 CriticalDatabaseConnections

**Severity**: critical
**Condition**: DB connections > 98% for 2m

```promql
(
  pg_stat_database_numbackends{datname="lia"}
  /
  pg_settings_max_connections
) * 100 > 98
```

**Team**: postgresql
**Receiver**: `database-team`
**Channels**: Email

---

#### 8.3 DatabaseDown

**Severity**: critical
**Condition**: PostgreSQL down for 1m

```promql
up{job="postgresql"} == 0
```

**Team**: postgresql
**Receiver**: `database-team`
**Channels**: Email

---

#### 8.4 SlowQueries

**Severity**: warning
**Condition**: High tuple fetch rate > 500k/s for 5m

```promql
rate(pg_stat_database_tup_fetched{datname="lia"}[5m]) > 500000
```

**Team**: postgresql
**Receiver**: `database-team`
**Channels**: Email

---

### Group 9: Application & Infrastructure Alerts (11 alerts)

**Purpose**: HTTP errors, latency, service uptime, disk, CPU, memory
**Interval**: 30s

**(11 alerts covering application performance and infrastructure resources - see `alerts.yml` lines 18-224 for full details)**

---

## 📬 Routing Configuration

AlertManager uses a tree-based routing structure to send alerts to appropriate receivers.

### Default Route

```yaml
route:
  receiver: 'default-email'
  group_by: ['alertname', 'component', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
```

**Parameters**:
- `receiver`: Fallback receiver if no child route matches
- `group_by`: Group alerts by these labels to reduce spam
- `group_wait`: Wait 30s before sending first notification (allows grouping)
- `group_interval`: Wait 5m before sending new alerts added to group
- `repeat_interval`: Re-send notification every 4h if still firing

### Child Routes

| Priority | Matcher | Receiver | Group Wait | Repeat | Continue |
|----------|---------|----------|------------|--------|----------|
| 1 | `severity: critical` | `critical-multi-channel` | 10s | 30m | No |
| 2 | `severity: warning` | `warning-email-slack` | 1m | 2h | No |
| 3 | `component: llm, severity: critical` | `llm-budget-critical` | 5s | 15m | No |
| 4 | `component: agents` | `agents-performance` | 1m | 1h | No |
| 5 | `component: postgresql` | `database-team` | 30s | 4h | No |
| 6 | `component: redis` | `redis-team` | 30s | 4h | No |
| 7 | `component: oauth, severity: critical` | `security-team` | 5s | 30m | No |

**Route Evaluation**:
1. Routes evaluated top-to-bottom
2. First matching route is used (`continue: false` stops evaluation)
3. If no route matches, default route is used

**Example Flow - Critical LLM Budget Alert**:
```
Alert Labels: {severity: "critical", component: "llm", alertname: "DailyCostBudgetExceeded"}

Route Matching:
1. severity: critical → ❌ Not matched (component-specific route has priority)
2. component: llm, severity: critical → ✅ MATCHED

Receiver: llm-budget-critical
Channels: Email (Finance + Ops) + Slack (#alerts-llm-budget)
Template: email.budget.html
Group Wait: 5s (immediate notification for budget alerts)
Repeat: Every 15 minutes if still firing
```

---

## 🚫 Inhibition Rules

Inhibition rules prevent notification spam by suppressing redundant alerts.

### Rule 1: Service Down → Suppress Errors/Latency

```yaml
- source_match:
    alertname: 'ServiceDown'
  target_match:
    component: 'api'
  target_match_re:
    alertname: '(HighErrorRate|HighLatency.*|CriticalLatency.*)'
  equal: ['service']
```

**Logic**: If service is down, high error rate and latency alerts are redundant.

**Example**:
- Source Alert: `ServiceDown` fires
- Suppressed: `HighErrorRate`, `HighLatencyP95`, `CriticalLatencyP99`
- Result: Only ServiceDown notification sent

---

### Rule 2: Redis Down → Suppress Connection Issues

```yaml
- source_match:
    alertname: 'RedisDown'
  target_match:
    component: 'redis'
  target_match_re:
    alertname: '(RedisConnectionsHigh|RedisMemoryHigh)'
```

**Logic**: If Redis is down, connection and memory alerts are redundant.

---

### Rule 3: PostgreSQL Down → Suppress Connection Pool

```yaml
- source_match:
    alertname: 'PostgreSQLDown'
  target_match:
    component: 'postgresql'
  target_match_re:
    alertname: '(HighDatabaseConnections|CriticalDatabaseConnections|SlowQueries)'
```

**Logic**: If database is down, connection pool and query alerts are redundant.

---

### Rule 4: Daily Budget → Suppress Weekly/Monthly

```yaml
- source_match:
    alertname: 'LLMDailyBudgetExceeded'
  target_match_re:
    alertname: '(LLMWeeklyBudgetExceeded|LLMMonthlyBudgetExceeded)'
  equal: ['component']
```

**Logic**: If daily budget is exceeded, weekly/monthly alerts add no value.

---

### Rule 5: Critical → Suppress Warnings

```yaml
- source_match:
    severity: 'critical'
  target_match:
    severity: 'warning'
  equal: ['alertname', 'component']
```

**Logic**: If critical alert is firing, warning for same issue is redundant.

**Example**:
- Source: `HITLClarificationFallbackCritical` (40% fallback rate)
- Suppressed: `HITLClarificationFallbackHigh` (20% threshold)
- Result: Only critical alert sent

---

## 📧 Receivers & Templates

### Receivers Overview

| Receiver | Channels | Template | Use Case |
|----------|----------|----------|----------|
| `default-email` | Email | `email.default.html` | Fallback for unmatched alerts |
| `critical-multi-channel` | Email + Slack + PagerDuty | `email.critical.html` | Critical severity alerts |
| `warning-email-slack` | Email + Slack | `email.warning.html` | Warning severity alerts |
| `llm-budget-critical` | Email + Slack | `email.budget.html` | LLM cost budget alerts |
| `agents-performance` | Email + Slack | `email.agents.html` | Agent SLA violations |
| `database-team` | Email | `email.database.html` | PostgreSQL alerts |
| `redis-team` | Email | `email.redis.html` | Redis alerts |
| `security-team` | Email + PagerDuty | `email.security.html` | OAuth security alerts |

### Template Features

#### 1. email.default.html (lines 1-60)

**Features**:
- Simple, clean design
- Alert severity badges (color-coded)
- Component labels
- Runbook section (if provided)
- Alert timestamps

**Use Case**: Generic alerts without specialized formatting needs

---

#### 2. email.critical.html (lines 62-131)

**Features**:
- 🚨 High-visibility red header
- Large "CRITICAL ALERT" title
- Priority banner
- Action-required checklist
- Escalation instructions (30min)
- Links to Grafana + Prometheus

**Use Case**: Severity: critical alerts requiring immediate action

**Example Email**:
```
🚨 CRITICAL ALERT
Immediate action required for LIA

⚠️ PRIORITY: CRITICAL

AgentsTTFTViolation
SLA TTFT violé pour intention email_search

📖 RUNBOOK - Follow these steps:
1. Vérifier la latence router (< 500ms)
2. Vérifier l'API OpenAI (latency network)
...

⚡ Action Required:
1. Acknowledge this alert immediately
2. Follow the runbook steps above
3. Escalate if not resolved within 30 minutes

On-call engineer: Please respond within 15 minutes.
```

---

#### 3. email.warning.html (lines 133-186)

**Features**:
- Orange header (warning color)
- "⚠️ Warning Alert" title
- Less urgent tone
- "Investigate when convenient" message

**Use Case**: Severity: warning alerts

---

#### 4. email.budget.html (lines 188-250)

**Features**:
- 💰 Cost-focused design
- Budget chart breakdown:
  - Current Cost (red, bold)
  - Budget Limit
  - Exceeded By
- Cost control recommendations
- Link to LLM Tokens & Cost dashboard

**Use Case**: LLM cost budget alerts (`llm-budget-critical` receiver)

**Example Email**:
```
💰 LLM Budget Alert
Cost threshold exceeded for LIA

DailyCostBudgetExceeded
Daily LLM cost budget exceeded

Budget Chart:
Current Cost:   12.50€ 🔴
Budget Limit:   5.00€
Exceeded By:    7.50€ 🔴

📖 Recommended Actions:
- Review high-cost requests in last 24h
- Check for runaway loops or batch operations
- Consider reducing max_tokens per request
```

---

#### 5. email.agents.html (lines 252-307)

**Features**:
- 🤖 Robot theme (purple gradient)
- SLA violation badge
- Intention label
- Monospace runbook for technical steps
- Link to Agents LangGraph dashboard

**Use Case**: Agent performance/SLA alerts (`agents-performance` receiver)

---

#### 6. email.database.html (lines 309-344)

**Features**:
- 🗄️ Database theme (blue gradient)
- Clean, professional layout

**Use Case**: PostgreSQL alerts (`database-team` receiver)

---

#### 7. email.redis.html (lines 346-381)

**Features**:
- 🔴 Redis theme (red gradient)
- Link to Infrastructure dashboard

**Use Case**: Redis alerts (`redis-team` receiver)

---

#### 8. email.security.html (lines 383-425)

**Features**:
- 🔒 Security theme (dark red)
- "SECURITY ALERT" title (all caps)
- Yellow security warning box
- "Immediate investigation required" emphasis
- Link to OAuth Security dashboard

**Use Case**: OAuth security incidents (`security-team` receiver)

**Example Email**:
```
🔒 SECURITY ALERT
OAuth security incident detected

PKCEValidationFailures
Échecs de validation PKCE détectés pour Google

5.2 échecs PKCE/s sur les 5 dernières minutes.
Possible attaque CSRF ou problème de cache Redis.

⚠️ SECURITY NOTICE: Immediate investigation required

Security Team: Please investigate immediately.
View OAuth metrics: OAuth Security Dashboard
```

---

### Template Variables Reference

All templates have access to:

```go
// Alert group metadata
.Status              // "firing" or "resolved"
.Alerts              // Array of all alerts in group
.Alerts.Firing       // Array of firing alerts
.Alerts.Resolved     // Array of resolved alerts
.GroupLabels         // Labels used for grouping
.CommonLabels        // Labels common to all alerts
.CommonAnnotations   // Annotations common to all alerts

// Per-alert data
.Labels.alertname    // Alert name (e.g., "HITLClarificationFallbackHigh")
.Labels.severity     // critical, warning, info
.Labels.component    // api, agents, postgresql, redis, oauth, etc.
.Labels.team         // ml, product, ops, security, etc.
.Labels.pagerduty    // "true" for PagerDuty alerts

.Annotations.summary      // One-line summary
.Annotations.description  // Detailed description
.Annotations.runbook      // Troubleshooting steps (multi-line)
.Annotations.dashboard    // Grafana dashboard URL
.Annotations.runbook_url  // External runbook URL

// Budget-specific (email.budget.html)
.Annotations.current_cost   // "12.50€"
.Annotations.budget_limit   // "5.00€"
.Annotations.exceeded_by    // "7.50€"

// Timestamps
.StartsAt            // Alert start time (RFC3339)
.EndsAt              // Alert end time (RFC3339, if resolved)
```

---

## ⚙️ Environment Configuration

### .env.alerting File

AlertManager configuration uses environment variables for sensitive data (SMTP credentials, API keys).

**Location**: `apps/api/.env.alerting`

**Template**: `apps/api/.env.alerting.example`

### Required Variables

#### SMTP Configuration

```bash
# Email sender address (appears in "From" field)
ALERTMANAGER_SMTP_FROM="alerts@lia.com"

# SMTP server and port
# Gmail: smtp.gmail.com:587
# SendGrid: smtp.sendgrid.net:587
# Mailgun: smtp.mailgun.org:587
ALERTMANAGER_SMTP_SMARTHOST="smtp.gmail.com:587"

# SMTP authentication username
ALERTMANAGER_SMTP_AUTH_USER="your-email@gmail.com"

# SMTP authentication password
# For Gmail: Use App Password (16 characters), NOT your regular password
# Generate at: https://myaccount.google.com/apppasswords
ALERTMANAGER_SMTP_AUTH_PASSWORD="abcd efgh ijkl mnop"

# Email recipients for critical alerts
# Supports multiple recipients: "ops@example.com,oncall@example.com"
ALERTMANAGER_EMAIL_TO_CRITICAL="ops-critical@lia.com"

# Email recipients for warning alerts
ALERTMANAGER_EMAIL_TO_WARNING="ops@lia.com"
```

### Optional Variables

#### Slack Integration

```bash
# Slack webhook URL for alert notifications
# Create webhook at: https://api.slack.com/apps → Incoming Webhooks
ALERTMANAGER_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
```

**Slack Channel Mapping**:
- `#alerts-critical` → Critical alerts (severity: critical)
- `#alerts-warning` → Warning alerts (severity: warning)
- `#alerts-llm-budget` → LLM budget alerts
- `#alerts-agents` → Agent performance alerts

#### PagerDuty Integration

```bash
# PagerDuty integration key (for critical alerts)
# Create integration at: PagerDuty → Services → Integrations → Prometheus
ALERTMANAGER_PAGERDUTY_SERVICE_KEY="your-pagerduty-integration-key"
```

**PagerDuty Triggers**:
- All `severity: critical` alerts with `pagerduty: "true"` label
- OAuth security alerts (PKCE/state validation failures)
- Redis rate limiting critical errors
- Service down alerts

---

### Environment-Specific Configuration

Create separate `.env.alerting` files per environment:

```bash
apps/api/
├── .env.alerting.development
├── .env.alerting.staging
└── .env.alerting.production
```

**Development**:
```bash
ALERTMANAGER_SMTP_FROM="alerts-dev@lia.com"
ALERTMANAGER_EMAIL_TO_CRITICAL="dev@lia.com"
ALERTMANAGER_EMAIL_TO_WARNING="dev@lia.com"
# Slack/PagerDuty disabled
```

**Staging**:
```bash
ALERTMANAGER_SMTP_FROM="alerts-staging@lia.com"
ALERTMANAGER_EMAIL_TO_CRITICAL="staging-oncall@lia.com"
ALERTMANAGER_SLACK_WEBHOOK_URL="https://hooks.slack.com/.../staging"
# PagerDuty disabled
```

**Production**:
```bash
ALERTMANAGER_SMTP_FROM="alerts@lia.com"
ALERTMANAGER_EMAIL_TO_CRITICAL="ops-critical@lia.com,oncall@lia.com"
ALERTMANAGER_SLACK_WEBHOOK_URL="https://hooks.slack.com/.../production"
ALERTMANAGER_PAGERDUTY_SERVICE_KEY="prod-integration-key"
```

---

## 🧪 Testing & Validation

### Test 1: SMTP Connection

Verify SMTP credentials before deploying AlertManager:

```bash
# Test SMTP connection (Python)
python3 << 'EOF'
import smtplib
import os
from dotenv import load_dotenv

# Load .env.alerting
load_dotenv('apps/api/.env.alerting')

smtp_host = os.getenv('ALERTMANAGER_SMTP_SMARTHOST', 'smtp.gmail.com:587').split(':')[0]
smtp_port = int(os.getenv('ALERTMANAGER_SMTP_SMARTHOST', 'smtp.gmail.com:587').split(':')[1])
username = os.getenv('ALERTMANAGER_SMTP_AUTH_USER')
password = os.getenv('ALERTMANAGER_SMTP_AUTH_PASSWORD')

print(f"Testing SMTP connection to {smtp_host}:{smtp_port}...")

try:
    server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
    server.starttls()
    server.login(username, password)
    print("✅ SMTP connection successful!")
    server.quit()
except Exception as e:
    print(f"❌ SMTP connection failed: {e}")
EOF
```

**Expected Output**:
```
Testing SMTP connection to smtp.gmail.com:587...
✅ SMTP connection successful!
```

---

### Test 2: AlertManager Configuration Validation

Validate AlertManager config syntax:

```bash
# Using amtool (AlertManager tool)
docker run --rm -v $(pwd)/infrastructure/observability/prometheus/alertmanager:/etc/alertmanager \
  prom/alertmanager:v0.27.0 \
  amtool check-config /etc/alertmanager/alertmanager.yml

# Expected output:
# Checking '/etc/alertmanager/alertmanager.yml'  SUCCESS
# Found:
#  - global config
#  - route
#  - 5 inhibit rules
#  - 8 receivers
```

---

### Test 3: Send Test Alert via API

Send a test alert to verify end-to-end flow:

```bash
# Critical test alert
curl -X POST http://localhost:9093/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestCriticalAlert",
      "severity": "critical",
      "component": "test",
      "team": "ops"
    },
    "annotations": {
      "summary": "This is a critical test alert",
      "description": "Testing AlertManager critical alert flow with multi-channel notifications.",
      "runbook": "1. Check email inbox\n2. Check Slack #alerts-critical\n3. Check PagerDuty (if configured)"
    },
    "startsAt": "2025-11-22T10:00:00Z",
    "endsAt": "2025-11-22T10:30:00Z"
  }
]'
```

**Expected Results**:
1. ✅ Email received at `ALERTMANAGER_EMAIL_TO_CRITICAL` within 10s
2. ✅ Slack message in `#alerts-critical` (if configured)
3. ✅ PagerDuty incident created (if configured)
4. ✅ Email uses `email.critical.html` template
5. ✅ Alert visible in AlertManager UI: http://localhost:9093

---

### Test 4: Warning Alert

```bash
# Warning test alert
curl -X POST http://localhost:9093/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestWarningAlert",
      "severity": "warning",
      "component": "test"
    },
    "annotations": {
      "summary": "This is a warning test alert",
      "description": "Testing AlertManager warning alert flow."
    },
    "startsAt": "2025-11-22T10:00:00Z"
  }
]'
```

**Expected Results**:
1. ✅ Email received at `ALERTMANAGER_EMAIL_TO_WARNING` within 1min (group_wait)
2. ✅ Slack message in `#alerts-warning` (if configured)
3. ✅ Email uses `email.warning.html` template
4. ❌ No PagerDuty incident (warning severity)

---

### Test 5: Budget Alert

```bash
# LLM budget test alert
curl -X POST http://localhost:9093/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestBudgetAlert",
      "severity": "critical",
      "component": "llm",
      "team": "finance"
    },
    "annotations": {
      "summary": "Daily LLM cost budget exceeded",
      "description": "Test alert for LLM budget monitoring",
      "current_cost": "12.50€",
      "budget_limit": "5.00€",
      "exceeded_by": "7.50€",
      "runbook": "1. Review high-cost requests\n2. Check for runaway loops\n3. Reduce max_tokens"
    },
    "startsAt": "2025-11-22T10:00:00Z"
  }
]'
```

**Expected Results**:
1. ✅ Email received at critical address within 5s (fast group_wait for budget)
2. ✅ Email uses `email.budget.html` template with cost breakdown
3. ✅ Slack message in `#alerts-llm-budget`

---

### Test 6: Inhibition Rules

Test that inhibition rules suppress redundant alerts:

```bash
# 1. Send ServiceDown alert
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {"alertname": "ServiceDown", "severity": "critical", "component": "api", "service": "lia-api"},
    "annotations": {"summary": "Service lia-api is down"},
    "startsAt": "2025-11-22T10:00:00Z"
  }
]'

# 2. Send HighErrorRate alert (should be inhibited)
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {"alertname": "HighErrorRate", "severity": "critical", "component": "api", "service": "lia-api"},
    "annotations": {"summary": "High error rate on lia-api"},
    "startsAt": "2025-11-22T10:00:01Z"
  }
]'

# 3. Check inhibited alerts
curl http://localhost:9093/api/v1/alerts | jq '.data.alerts[] | select(.status.inhibitedBy | length > 0)'
```

**Expected Result**:
- `ServiceDown` notification sent
- `HighErrorRate` notification **NOT** sent (inhibited)
- API shows `HighErrorRate` alert with `inhibitedBy: ["ServiceDown"]`

---

### Test 7: Resolved Alerts

Test that resolved alerts send notifications:

```bash
# 1. Send firing alert
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {"alertname": "TestResolvedAlert", "severity": "warning", "component": "test"},
    "annotations": {"summary": "This alert will be resolved"},
    "startsAt": "2025-11-22T10:00:00Z"
  }
]'

# 2. Wait 1 minute for firing notification

# 3. Send resolved alert (endsAt in past)
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {"alertname": "TestResolvedAlert", "severity": "warning", "component": "test"},
    "annotations": {"summary": "This alert will be resolved"},
    "startsAt": "2025-11-22T10:00:00Z",
    "endsAt": "2025-11-22T10:05:00Z"
  }
]'
```

**Expected Result**:
- First email: "Status: firing"
- Second email: "Status: resolved" (green color in template)

---

## 🔇 Silencing Alerts

Silences suppress alert notifications during maintenance windows or known issues.

### Via API

```bash
# Create silence for 2 hours
curl -X POST http://localhost:9093/api/v1/silences -H "Content-Type: application/json" -d '{
  "matchers": [
    {
      "name": "alertname",
      "value": "HighLatencyP95",
      "isRegex": false,
      "isEqual": true
    },
    {
      "name": "component",
      "value": "api",
      "isRegex": false,
      "isEqual": true
    }
  ],
  "startsAt": "2025-11-22T14:00:00Z",
  "endsAt": "2025-11-22T16:00:00Z",
  "createdBy": "ops-team",
  "comment": "Planned database migration - expect higher latency"
}'

# Response includes silence ID
{"silenceID": "8c5c3f3a-1b2c-4d5e-8f9a-1234567890ab"}
```

### Via UI

1. Navigate to http://localhost:9093
2. Click **"Silences"** tab
3. Click **"New Silence"** button
4. Configure matchers:
   - `alertname` = `HighLatencyP95`
   - `component` = `api`
5. Set duration (e.g., 2 hours)
6. Add comment: "Planned database migration"
7. Click **"Create"**

### Silence All Alerts for Component

```bash
# Silence all Redis alerts for 1 hour
curl -X POST http://localhost:9093/api/v1/silences -d '{
  "matchers": [{"name": "component", "value": "redis"}],
  "startsAt": "2025-11-22T14:00:00Z",
  "endsAt": "2025-11-22T15:00:00Z",
  "createdBy": "ops-team",
  "comment": "Redis maintenance window"
}'
```

### Delete Silence

```bash
# Delete silence by ID
curl -X DELETE http://localhost:9093/api/v1/silence/8c5c3f3a-1b2c-4d5e-8f9a-1234567890ab
```

### List Active Silences

```bash
# Get all silences
curl http://localhost:9093/api/v1/silences | jq '.data[] | {id: .id, createdBy: .createdBy, comment: .comment, status: .status.state}'
```

**Example Output**:
```json
{
  "id": "8c5c3f3a-1b2c-4d5e-8f9a-1234567890ab",
  "createdBy": "ops-team",
  "comment": "Planned database migration",
  "status": "active"
}
```

---

## 📊 Monitoring AlertManager

### Metrics Exposed

AlertManager exposes Prometheus metrics on `http://localhost:9093/metrics`:

```promql
# Number of active alerts
alertmanager_alerts

# Total notifications sent
alertmanager_notifications_total

# Failed notifications
alertmanager_notifications_failed_total

# Active silences
alertmanager_silences_active

# Notification latency
alertmanager_notification_latency_seconds
```

### Grafana Dashboard

Import official AlertManager dashboard:

1. Navigate to Grafana: http://localhost:3000
2. Click **"+"** → **"Import"**
3. Enter dashboard ID: **9578**
4. Select Prometheus datasource
5. Click **"Import"**

**Dashboard URL**: https://grafana.com/grafana/dashboards/9578

**Panels Include**:
- Active alerts
- Notification rate
- Failed notifications
- Silence count
- Alert processing duration

---

## 🔐 Security Best Practices

### 1. Use Environment Variables

**❌ BAD** - Hardcoded credentials:
```yaml
smtp_auth_password: 'my-secret-password'
```

**✅ GOOD** - Environment variables:
```yaml
smtp_auth_password: '{{ env "ALERTMANAGER_SMTP_AUTH_PASSWORD" }}'
```

### 2. Use App Passwords (Gmail)

**For Gmail SMTP**:
1. Enable 2FA on your Google account: https://myaccount.google.com/security
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use 16-character app password (e.g., `abcd efgh ijkl mnop`)
4. **NEVER** use your regular Gmail password

### 3. Restrict AlertManager Access

**Firewall Rules** (Linux):
```bash
# Only allow Prometheus to connect to AlertManager
iptables -A INPUT -p tcp --dport 9093 -s <prometheus-ip> -j ACCEPT
iptables -A INPUT -p tcp --dport 9093 -j DROP
```

**Docker Network Isolation**:
```yaml
services:
  alertmanager:
    networks:
      - monitoring  # Internal network only
    # Don't expose port 9093 to host (only accessible via Docker network)
```

### 4. Use TLS for AlertManager

Enable HTTPS for AlertManager UI:

```yaml
# alertmanager.yml
global:
  http_config:
    tls_config:
      cert_file: /etc/alertmanager/tls/cert.pem
      key_file: /etc/alertmanager/tls/key.pem
```

### 5. Secure Webhook URLs

**Slack Webhooks**:
- Use environment variables: `{{ env "ALERTMANAGER_SLACK_WEBHOOK_URL" }}`
- Rotate webhooks if compromised
- Restrict webhook to specific channels

**PagerDuty Keys**:
- Use separate integration keys per environment (dev/staging/prod)
- Rotate keys quarterly

### 6. Audit Alert Access

Monitor who is viewing/silencing alerts:

```bash
# AlertManager audit logs
docker logs lia-alertmanager | grep -i "silence"
```

---

## 🆘 Troubleshooting

### Issue 1: Alerts Not Received

**Symptoms**: Alert firing in Prometheus, but no email/Slack notification

**Diagnosis Steps**:

```bash
# 1. Check AlertManager is healthy
curl http://localhost:9093/-/healthy
# Expected: "Healthy"

# 2. Verify Prometheus is sending alerts to AlertManager
curl http://localhost:9090/api/v1/alertmanagers | jq
# Expected: "activeAlertmanagers": [{"url": "http://alertmanager:9093/api/v2/alerts"}]

# 3. Check alerts in AlertManager
curl http://localhost:9093/api/v1/alerts | jq '.data.alerts[] | {name: .labels.alertname, state: .status.state}'

# 4. Check for notification errors
docker logs lia-alertmanager | grep -i "error"

# 5. Verify SMTP configuration
docker logs lia-alertmanager | grep -i "smtp"
```

**Common Causes**:
1. ❌ Prometheus not configured with AlertManager address
2. ❌ Alert silenced
3. ❌ Alert inhibited by another alert
4. ❌ SMTP credentials incorrect
5. ❌ Firewall blocking SMTP port 587

**Fix**:
```bash
# Reload AlertManager configuration
curl -X POST http://localhost:9093/-/reload

# Test SMTP manually (see Test 1 above)

# Check silences
curl http://localhost:9093/api/v1/silences | jq '.data[] | select(.status.state == "active")'
```

---

### Issue 2: Alert Spamming

**Symptoms**: Receiving too many duplicate notifications

**Diagnosis**:

```bash
# Check notification rate
curl http://localhost:9093/metrics | grep alertmanager_notifications_total

# Check grouping configuration
curl http://localhost:9093/api/v1/status | jq '.config.route'
```

**Fixes**:

**1. Increase group_interval**:
```yaml
route:
  group_interval: 10m  # Increase from 5m to 10m
```

**2. Increase repeat_interval**:
```yaml
route:
  repeat_interval: 8h  # Increase from 4h to 8h
```

**3. Add inhibition rules**:
```yaml
inhibit_rules:
  - source_match:
      alertname: 'HighErrorRate'
    target_match:
      alertname: 'HighLatencyP95'
    equal: ['service']
```

**4. Create silence for known issue**:
```bash
curl -X POST http://localhost:9093/api/v1/silences -d '{...}'
```

---

### Issue 3: Configuration Errors

**Symptoms**: AlertManager fails to start

**Diagnosis**:

```bash
# View AlertManager logs
docker logs lia-alertmanager

# Validate configuration syntax
docker run --rm -v $(pwd)/infrastructure/observability/prometheus/alertmanager:/etc/alertmanager \
  prom/alertmanager:v0.27.0 \
  amtool check-config /etc/alertmanager/alertmanager.yml
```

**Common Errors**:

**Error**: `undefined variable "$ALERTMANAGER_SMTP_AUTH_PASSWORD"`

**Fix**: Ensure environment variables are loaded:
```yaml
services:
  alertmanager:
    env_file:
      - ./apps/api/.env.alerting  # Add this
```

**Error**: `template "email.budget.html" not defined`

**Fix**: Mount templates directory:
```yaml
volumes:
  - ./infrastructure/observability/prometheus/alertmanager:/etc/alertmanager
```

---

### Issue 4: Slack Notifications Not Working

**Diagnosis**:

```bash
# 1. Check Slack webhook URL is set
docker exec lia-alertmanager env | grep SLACK

# 2. Test webhook manually
curl -X POST "$ALERTMANAGER_SLACK_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test message from AlertManager"}'

# 3. Check AlertManager logs for Slack errors
docker logs lia-alertmanager | grep -i "slack"
```

**Common Causes**:
1. ❌ Webhook URL incorrect or expired
2. ❌ Channel doesn't exist (e.g., `#alerts-critical`)
3. ❌ Slack app not installed in workspace

**Fix**:
1. Regenerate webhook: https://api.slack.com/apps → Incoming Webhooks
2. Create missing channels in Slack
3. Update `.env.alerting` with new webhook URL

---

### Issue 5: PagerDuty Incidents Not Created

**Diagnosis**:

```bash
# Check PagerDuty integration key is set
docker exec lia-alertmanager env | grep PAGERDUTY

# Check AlertManager logs for PagerDuty errors
docker logs lia-alertmanager | grep -i "pagerduty"
```

**Common Causes**:
1. ❌ Integration key incorrect
2. ❌ Alert doesn't have `pagerduty: "true"` label
3. ❌ PagerDuty service deactivated

**Fix**:
1. Verify integration key: PagerDuty → Services → Integrations → Prometheus
2. Ensure critical alerts have correct label in `alerts.yml`
3. Check PagerDuty service status

---

## 📚 References

### Official Documentation

- [Prometheus Alerting Overview](https://prometheus.io/docs/alerting/latest/overview/)
- [AlertManager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Notification Template Reference](https://prometheus.io/docs/alerting/latest/notifications/)
- [AlertManager API](https://prometheus.io/docs/alerting/latest/management_api/)
- [Alerting Rules Best Practices](https://prometheus.io/docs/practices/alerting/)

### LIA Documentation

- [Observability README](../README.md)
- [Prometheus Recording Rules](../prometheus/recording_rules.yml)
- [Alert Rules (Infrastructure)](../prometheus/alerts.yml)
- [Alert Rules (HITL Quality)](../prometheus/alert_rules.yml)
- [Grafana Dashboards](../grafana/dashboards/README.md)

### External Resources

- [AlertManager GitHub](https://github.com/prometheus/alertmanager)
- [Grafana AlertManager Dashboard](https://grafana.com/grafana/dashboards/9578)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [PagerDuty Prometheus Integration](https://www.pagerduty.com/docs/guides/prometheus-integration-guide/)

---

## 📝 Changelog

### 2.0 (2025-11-22)

**Added**:
- 57 alert rules documented exhaustively (previously 0 documented)
- 10 HITL quality alerts (new group)
- 9 Redis rate limiting alerts (new group)
- 6 OAuth security alerts (new group)
- 6 Conversations alerts (new group)
- 8 specialized email templates documented
- Environment configuration section
- Testing & validation procedures (7 tests)
- Inhibition rules documentation (5 rules)
- Routing configuration tree
- Security best practices
- Troubleshooting guide (5 common issues)

**Changed**:
- README structure reorganized for clarity
- Alert rules grouped by domain (HITL, Agents, Redis, etc.)
- Added alert statistics tables
- Expanded Docker Compose example with healthcheck
- Added environment-specific config examples

**Total Lines**: 1913 (vs 510 previously - 3.7x expansion)

---

### 1.0 (2025-11-20)

- Initial production-ready AlertManager configuration
- Basic routing, inhibition, receivers
- 8 email templates
- Quick start guide

---

## 🎯 Next Steps

After configuring AlertManager:

1. ✅ Configure environment variables (`.env.alerting`)
2. ✅ Test SMTP connection
3. ✅ Send test alert (verify end-to-end)
4. ✅ Configure Slack webhook (optional but recommended)
5. ✅ Configure PagerDuty (optional, for critical alerts)
6. ✅ Import AlertManager Grafana dashboard (ID: 9578)
7. ✅ Create runbooks for critical alerts (external documentation)
8. ✅ Set up on-call rotation (PagerDuty schedules)
9. ✅ Document escalation procedures
10. ✅ Train team on AlertManager UI (silencing, filtering)

**Related Documentation**:
- [Main Observability README](../README.md) - Overview of full stack
- [Prometheus Alert Rules](../prometheus/alert_rules.yml) - HITL quality rules
- [Infrastructure Alerts](../prometheus/alerts.yml) - Application/infrastructure rules
- [Grafana Dashboards](../grafana/dashboards/README.md) - Visualization layer

---

**Document Maintained By**: Infrastructure Team
**Last Updated**: 2025-11-22
**Review Frequency**: Monthly
**Feedback**: Create issue in repository or contact ops-team@lia.com
