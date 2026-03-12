# AlertManager Configuration - LIA

**Production-ready multi-channel alert routing and notification system**

**Version**: 1.0.0
**Date**: 2025-11-23
**AlertManager**: v0.27.0

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Configuration](#configuration)
4. [Routing Strategy](#routing-strategy)
5. [Email Templates](#email-templates)
6. [Slack Integration](#slack-integration)
7. [PagerDuty Integration](#pagerduty-integration)
8. [Inhibition Rules](#inhibition-rules)
9. [Deployment](#deployment)
10. [Testing](#testing)
11. [Troubleshooting](#troubleshooting)
12. [References](#references)

---

## Overview

This AlertManager configuration provides **enterprise-grade alert routing** with:

- **Multi-channel notifications**: Email, Slack, PagerDuty
- **Intelligent routing**: By severity, component, and team
- **Inhibition rules**: Prevent alert storms
- **Grouping**: Reduce notification spam
- **Professional templates**: HTML email templates with runbook links
- **Environment variable substitution**: Dynamic configuration at runtime

### Key Features

✅ **4 team-specific email routing** (Backend, Finance, Security, ML)
✅ **3 severity levels** (Critical → Multi-channel, Warning → Email+Slack, Info → Email only)
✅ **7 component-specific routes** (LLM Budget, Agents, Database, Redis, OAuth, HITL)
✅ **8 inhibition rules** (Prevent cascade alerts)
✅ **Professional HTML email templates** (Critical/Warning/Budget/Agents/Database/Redis/Security)
✅ **Optional Slack integration** (3 webhooks: Critical/Warning/Security)
✅ **Optional PagerDuty integration** (Critical alerts 24/7)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Prometheus                              │
│                    (Alert Evaluation)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ Firing Alerts
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│                        AlertManager                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Routing Tree (Route Evaluation)             │  │
│  │                                                          │  │
│  │  Root Route (group_by: alertname, component, severity)  │  │
│  │  ├─ Critical → critical-multi-channel (10s wait)        │  │
│  │  ├─ Warning → warning-email-slack (1m wait)             │  │
│  │  ├─ LLM Budget → llm-budget-finance (5s wait)           │  │
│  │  ├─ Agents → agents-ml-team (1m wait)                   │  │
│  │  ├─ Database → database-backend-team                    │  │
│  │  ├─ Redis → redis-backend-team                          │  │
│  │  ├─ OAuth Security → security-team-critical (5s wait)   │  │
│  │  ├─ HITL → hitl-ml-team                                 │  │
│  │  └─ Default → default-email                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │            Inhibition Rules (Suppress Cascade)           │  │
│  │                                                          │  │
│  │  • ServiceDown → Inhibits HighErrorRate, HighLatency    │  │
│  │  • RedisDown → Inhibits RedisConnectionsHigh            │  │
│  │  • PostgreSQLDown → Inhibits DB connection alerts       │  │
│  │  • ContainerDown → Inhibits container metrics           │  │
│  │  • DailyBudget → Inhibits Weekly/Monthly budget alerts  │  │
│  │  • Critical → Inhibits Warning (same component)         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Receivers                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└────┬────────┬────────┬────────┬────────┬────────┬─────────┬───┘
     │        │        │        │        │        │         │
     ↓        ↓        ↓        ↓        ↓        ↓         ↓
  Email    Email    Email    Email   Slack    Slack    PagerDuty
 Backend  Finance Security   ML    Critical Warning   Critical
   Team    Team     Team    Team   Channel  Channel    24/7
```

---

## Configuration

### Required Environment Variables

**SMTP Configuration** (all required):
```bash
ALERTMANAGER_SMTP_FROM=alertmanager@lia.ai
ALERTMANAGER_SMTP_SMARTHOST=smtp.gmail.com:587
ALERTMANAGER_SMTP_AUTH_USERNAME=alertmanager@lia.ai
ALERTMANAGER_SMTP_AUTH_PASSWORD=your-app-password
```

**Email Recipients** (Backend required, others optional with fallback):
```bash
ALERTMANAGER_BACKEND_TEAM_EMAIL=backend-team@lia.ai
ALERTMANAGER_FINANCE_TEAM_EMAIL=finance@lia.ai          # Falls back to backend
ALERTMANAGER_SECURITY_TEAM_EMAIL=security@lia.ai        # Falls back to backend
ALERTMANAGER_ML_TEAM_EMAIL=ml-team@lia.ai               # Falls back to backend
```

### Optional Environment Variables

**Slack Webhooks** (leave empty to disable):
```bash
ALERTMANAGER_SLACK_WEBHOOK_CRITICAL=https://hooks.slack.com/services/T.../B.../xxx
ALERTMANAGER_SLACK_WEBHOOK_WARNING=https://hooks.slack.com/services/T.../B.../xxx
ALERTMANAGER_SLACK_WEBHOOK_SECURITY=https://hooks.slack.com/services/T.../B.../xxx
```

**PagerDuty** (leave empty to disable):
```bash
ALERTMANAGER_PAGERDUTY_ROUTING_KEY=your-integration-key
```

### Configuration Files

```
apps/api/monitoring/alertmanager/
├── alertmanager.yml.template       # Jinja2 template with ${VAR} syntax
├── docker-entrypoint.sh            # Variable substitution script
├── templates/
│   └── email.tmpl                  # HTML email templates
└── README.md                       # This file
```

---

## Routing Strategy

### Severity-Based Routing

| Severity | Channels | Group Wait | Repeat Interval | Use Case |
|----------|----------|------------|-----------------|----------|
| **Critical** | Email + Slack + PagerDuty | 10s | 30m | Production incidents requiring immediate attention |
| **Warning** | Email + Slack | 1m | 2h | Performance degradation, approaching thresholds |
| **Info** | Email | 30s | 4h | Informational alerts, low-priority issues |

### Component-Based Routing

| Component | Team | Special Handling | Example Alerts |
|-----------|------|------------------|----------------|
| **llm (Budget)** | Finance + Backend | 5s wait (immediate) | DailyCostBudgetExceeded, ModelCostBudgetExceeded |
| **agents** | ML Team | 1m wait | AgentsTTFTViolation, AgentsTokensPerSecondLow |
| **postgresql** | Backend | Default grouping | HighDatabaseConnections, SlowQueries |
| **redis** | Backend | Default grouping | RedisMemoryHigh, RedisConnectionsHigh |
| **oauth** | Security + Backend | 5s wait (critical only) | HighOAuthFailureRate, PKCEValidationFailures |
| **hitl** | ML Team | 30s wait | HITLClarificationFallbackHigh |

### Grouping Strategy

```yaml
group_by: ['alertname', 'component', 'severity']
group_wait: 30s      # Wait before sending first notification
group_interval: 5m   # Wait before sending updates
repeat_interval: 4h  # Re-send if alert still firing
```

**Example**: If 5 `HighErrorRate` alerts fire for different API endpoints within 30s, they will be grouped into **1 notification** instead of 5 separate emails.

---

## Email Templates

### Available Templates

Located in `templates/email.tmpl`:

1. **email.default.html** - Standard alert notification
2. **email.critical.html** - Red-themed critical alerts with priority badge
3. **email.warning.html** - Yellow-themed warning alerts
4. **email.budget.html** - Budget-specific template with cost details
5. **email.agents.html** - Agent performance alerts with SLA info
6. **email.database.html** - Database alerts
7. **email.redis.html** - Redis alerts
8. **email.security.html** - Security-themed alerts

### Template Features

- **Responsive HTML design** (mobile-friendly)
- **Color-coded severity** (Critical=Red, Warning=Orange, Info=Blue)
- **Runbook links** (if `runbook_url` annotation present)
- **Grafana dashboard links** (if `grafana_url` annotation present)
- **Alert metadata table** (severity, component, started time)
- **Resolved alerts section** (shows when alerts recover)

### Example Email Output

```
Subject: [CRITICAL] LIA: HighDatabaseConnections

⚠️ PRIORITY: CRITICAL

HighDatabaseConnections

PostgreSQL connection pool is at 92% capacity (critical threshold: 90%)

Severity: CRITICAL
Component: postgresql

Runbook: https://runbooks.lia.ai/database/high-connections
Dashboard: https://grafana.lia.ai/d/database-performance

Started: 2025-11-23 14:30:00
```

---

## Slack Integration

### Setup

1. **Create Slack App** at https://api.slack.com/apps
2. **Enable Incoming Webhooks**
3. **Add to Workspace** and select channels:
   - `#alerts-critical` for critical alerts
   - `#alerts-warning` for warnings
   - `#alerts-security` for security issues
4. **Copy Webhook URLs** and set environment variables

### Message Format

Critical alert example:
```
🔥 CRITICAL: HighErrorRate

Alert: HighErrorRate
Severity: critical
Component: api
Summary: API error rate is 12% (threshold: 5%)
Description: User-facing API endpoints are experiencing elevated error rates
Runbook: https://runbooks.lia.ai/api/high-error-rate
```

### Features

- **Color-coded messages** (Red for critical, Orange for warning, Green for resolved)
- **Structured Slack blocks** (easy to scan)
- **Runbook links** (one-click access to remediation steps)
- **Resolved notifications** (confirms when issue is fixed)

---

## PagerDuty Integration

### Setup

1. **Create PagerDuty Service** for LIA
2. **Add Integration** → Events API v2
3. **Copy Routing Key** and set `ALERTMANAGER_PAGERDUTY_ROUTING_KEY`

### Routing

PagerDuty is triggered for:
- **All critical alerts** (severity=critical)
- **Security alerts** (component=oauth + severity=critical)

PagerDuty incidents include:
- Alert name and component
- Firing/resolved count
- Summary annotation
- Automatic resolution when alert resolves

### Example Incident

```
Title: [critical] HighErrorRate - api
Description: API error rate is 12% (threshold: 5%)
Details:
  - Firing: 3 alerts
  - Resolved: 0 alerts
  - Summary: User-facing API endpoints experiencing elevated error rates
```

---

## Inhibition Rules

Inhibition rules **suppress lower-priority alerts** when higher-priority alerts are firing, preventing alert fatigue.

### Configured Inhibition Rules

1. **ServiceDown** → Inhibits `HighErrorRate`, `HighLatency*`, `CriticalLatency*` (same service)
   - **Rationale**: If service is down, high error rate is expected

2. **RedisDown** → Inhibits `RedisConnectionsHigh`, `RedisMemoryHigh`
   - **Rationale**: If Redis is down, connection/memory alerts are redundant

3. **PostgreSQLDown** → Inhibits `HighDatabaseConnections`, `CriticalDatabaseConnections`, `SlowQueries`
   - **Rationale**: If database is down, connection pool alerts are irrelevant

4. **ContainerDown** → Inhibits `HighCPUUsage`, `HighMemoryUsage`, `ContainerRestartingFrequently` (same container)
   - **Rationale**: If container is down, resource usage alerts are meaningless

5. **DailyBudgetExceeded** → Inhibits `WeeklyBudgetExceeded`, `MonthlyBudgetExceeded`
   - **Rationale**: Daily budget exceeded implies weekly/monthly will also be exceeded

6. **LLMAPIFailureRateHigh** → Inhibits `.*Latency.*` (same component)
   - **Rationale**: If LLM API is failing, latency alerts are noise

7. **Critical severity** → Inhibits Warning severity (same alertname + component)
   - **Rationale**: If critical alert is firing, warning alert is redundant

### Example

```
Scenario: PostgreSQL database crashes

Without inhibition:
  ❌ PostgreSQLDown (critical)
  ❌ HighDatabaseConnections (warning) - NOISE
  ❌ CriticalDatabaseConnections (critical) - NOISE
  ❌ SlowQueries (warning) - NOISE
  → 4 notifications

With inhibition:
  ✅ PostgreSQLDown (critical)
  🔇 HighDatabaseConnections (inhibited)
  🔇 CriticalDatabaseConnections (inhibited)
  🔇 SlowQueries (inhibited)
  → 1 notification

Result: 75% reduction in alert noise
```

---

## Deployment

### Prerequisites

1. **SMTP credentials** (Gmail App Password, SendGrid API key, or corporate SMTP)
2. **Docker** and docker-compose installed
3. **Environment variables** set in `.env` file

### Step 1: Configure Environment

```bash
# Copy example configuration
cp apps/api/.env.alerting.example apps/api/.env.alerting

# Edit with your values
nano apps/api/.env.alerting

# Required variables
ALERTMANAGER_SMTP_FROM=alertmanager@yourdomain.com
ALERTMANAGER_SMTP_SMARTHOST=smtp.gmail.com:587
ALERTMANAGER_SMTP_AUTH_USERNAME=your-email@gmail.com
ALERTMANAGER_SMTP_AUTH_PASSWORD=your-app-password
ALERTMANAGER_BACKEND_TEAM_EMAIL=backend@yourdomain.com

# Optional: Slack/PagerDuty
ALERTMANAGER_SLACK_WEBHOOK_CRITICAL=https://hooks.slack.com/...
ALERTMANAGER_PAGERDUTY_ROUTING_KEY=your-key
```

### Step 2: Start AlertManager

```bash
# Start AlertManager container
docker-compose -f docker-compose.dev.yml up -d alertmanager

# View logs to verify startup
docker logs -f lia-alertmanager-dev
```

**Expected output:**
```
================================================================
AlertManager Configuration Rendering
================================================================

[1/3] Validating required environment variables...
  OK - All required variables are set

[2/3] Setting defaults for optional variables...
  OK - Defaults set

[3/3] Rendering configuration template...
  OK - Configuration rendered successfully

================================================================
Configuration Summary
================================================================
SMTP Server:        smtp.gmail.com:587
SMTP From:          alertmanager@yourdomain.com
Backend Team Email: backend@yourdomain.com
Finance Team Email: finance@yourdomain.com
Security Team Email: security@yourdomain.com
ML Team Email:      ml-team@yourdomain.com

Optional Integrations:
  Slack Critical:   CONFIGURED
  Slack Warning:    NOT CONFIGURED (email only)
  Slack Security:   NOT CONFIGURED (email only)
  PagerDuty:        CONFIGURED

================================================================
Starting AlertManager...
================================================================
```

### Step 3: Verify AlertManager UI

Open browser to: http://localhost:9094

You should see:
- **Status**: Active configuration loaded
- **Receivers**: List of configured receivers (email, Slack, PagerDuty)
- **Silences**: Empty (no silences configured)
- **Alerts**: Empty (no alerts firing initially)

### Step 4: Link Prometheus to AlertManager

Verify Prometheus is configured to send alerts:

```bash
# Check Prometheus logs
docker logs lia-prometheus-dev | grep alertmanager
```

Expected output:
```
msg="Notifying AlertManager" url=http://alertmanager:9093
```

---

## Testing

### Test 1: Manual Test Alert

Send a test alert to AlertManager:

```bash
# Create test alert
curl -X POST http://localhost:9094/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "component": "testing"
    },
    "annotations": {
      "summary": "Test alert from manual test",
      "description": "This is a test alert to verify AlertManager is working correctly"
    }
  }
]'
```

**Expected result:**
- Email received at `ALERTMANAGER_BACKEND_TEAM_EMAIL` within 1 minute
- AlertManager UI shows 1 active alert
- If Slack configured: Message in `#alerts-warning` channel

### Test 2: Validate Configuration

Check AlertManager configuration is valid:

```bash
# Inside AlertManager container
docker exec lia-alertmanager-dev amtool check-config /etc/alertmanager/alertmanager.yml
```

Expected output:
```
Checking '/etc/alertmanager/alertmanager.yml'  SUCCESS
Found:
 - global config
 - route
 - 8 inhibit rules
 - 10 receivers
 - 7 templates
```

### Test 3: Validate Routing

Test that alerts route to correct receivers:

```bash
# Test critical alert routing
curl -X POST http://localhost:9094/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "TestCriticalAlert",
      "severity": "critical",
      "component": "api"
    },
    "annotations": {
      "summary": "Critical test alert",
      "description": "Testing multi-channel routing for critical alerts"
    }
  }
]'
```

**Expected routing:**
- Email to Backend team ✅
- Slack message in `#alerts-critical` (if configured) ✅
- PagerDuty incident created (if configured) ✅

### Test 4: Validate Inhibition

Test that inhibition rules work:

```bash
# Send source alert (PostgreSQLDown)
curl -X POST http://localhost:9094/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "PostgreSQLDown",
      "component": "postgresql",
      "severity": "critical"
    },
    "annotations": {
      "summary": "PostgreSQL database is down"
    }
  }
]'

# Send target alert (should be inhibited)
curl -X POST http://localhost:9094/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "HighDatabaseConnections",
      "component": "postgresql",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Database connection pool is high"
    }
  }
]'
```

**Expected behavior:**
- Notification sent for `PostgreSQLDown` ✅
- NO notification sent for `HighDatabaseConnections` (inhibited) ✅

Check AlertManager UI: `HighDatabaseConnections` should show **"Inhibited"** status.

---

## Troubleshooting

### Issue: AlertManager container fails to start

**Symptom:**
```
ERROR: Missing required environment variables: ALERTMANAGER_SMTP_AUTH_PASSWORD
```

**Solution:**
1. Check `.env` file contains all required variables
2. Verify docker-compose.dev.yml includes `env_file: ./apps/api/.env`
3. Restart container: `docker-compose -f docker-compose.dev.yml up -d alertmanager`

---

### Issue: Emails not being sent

**Symptom:** Alerts fire in Prometheus but no emails received

**Diagnosis:**
```bash
# Check AlertManager logs
docker logs lia-alertmanager-dev | grep -i error

# Check AlertManager received the alert
curl http://localhost:9094/api/v1/alerts | jq '.data[] | select(.labels.alertname=="TestAlert")'
```

**Common causes:**

1. **SMTP credentials invalid:**
   - Verify `ALERTMANAGER_SMTP_AUTH_USERNAME` and `ALERTMANAGER_SMTP_AUTH_PASSWORD`
   - For Gmail: Use App Password, not regular password
   - Test SMTP manually: `telnet smtp.gmail.com 587`

2. **Firewall blocking SMTP:**
   - Check port 587 is open
   - Try alternate port: 465 (SSL) or 2525

3. **Email in spam folder:**
   - Check spam/junk folder
   - Whitelist `ALERTMANAGER_SMTP_FROM` address

4. **AlertManager not linked to Prometheus:**
   - Check Prometheus config: `--alertmanager.url=http://alertmanager:9093`
   - Verify Prometheus logs show "Notifying AlertManager"

---

### Issue: Slack notifications not working

**Symptom:** Emails work but Slack messages not appearing

**Diagnosis:**
```bash
# Check if webhook is configured
docker exec lia-alertmanager-dev printenv | grep SLACK

# Check AlertManager logs for Slack errors
docker logs lia-alertmanager-dev | grep -i slack
```

**Common causes:**

1. **Webhook URL empty:**
   - Verify `ALERTMANAGER_SLACK_WEBHOOK_CRITICAL` is set and not empty
   - Webhook should start with `https://hooks.slack.com/services/`

2. **Webhook URL invalid:**
   - Test webhook manually:
     ```bash
     curl -X POST -H 'Content-type: application/json' \
       --data '{"text":"Test from AlertManager"}' \
       https://hooks.slack.com/services/YOUR/WEBHOOK/URL
     ```
   - Should return `ok`

3. **Channel does not exist:**
   - Verify channel `#alerts-critical` exists in Slack workspace
   - AlertManager app must be invited to channel: `/invite @AlertManager`

---

### Issue: Alerts not being inhibited

**Symptom:** Receiving cascade alerts despite inhibition rules

**Diagnosis:**
```bash
# Check AlertManager UI: http://localhost:9094/#/silences
# Look for "Inhibited" status on alerts

# Check inhibition rules loaded
docker exec lia-alertmanager-dev amtool config routes show
```

**Common causes:**

1. **Labels do not match:**
   - Inhibition requires `equal: ['component']` labels to match EXACTLY
   - Check alert labels in Prometheus: `up{component="postgresql"}`
   - Verify source and target alerts have same component label

2. **Alert not in inhibition rule:**
   - Review `inhibit_rules` section in `alertmanager.yml.template`
   - Add missing inhibition rules if needed

3. **Timing issue:**
   - Source alert must be **firing first** before target alert
   - If target fires before source, it will not be inhibited

---

### Issue: PagerDuty incidents not created

**Symptom:** Critical alerts fire but no PagerDuty incident

**Diagnosis:**
```bash
# Check routing key configured
docker exec lia-alertmanager-dev printenv | grep PAGERDUTY

# Check AlertManager logs for PagerDuty errors
docker logs lia-alertmanager-dev | grep -i pagerduty
```

**Common causes:**

1. **Routing key invalid:**
   - Verify `ALERTMANAGER_PAGERDUTY_ROUTING_KEY` is 32-character hex string
   - Get correct key from PagerDuty: Service → Integrations → Events API v2

2. **Wrong severity:**
   - PagerDuty only triggers for `severity: critical`
   - Check alert has `labels: { severity: "critical" }`

3. **Firewall blocking PagerDuty API:**
   - PagerDuty requires outbound HTTPS to `events.pagerduty.com`
   - Check network allows HTTPS to PagerDuty

---

## References

### Official Documentation

- [AlertManager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [AlertManager Routing Tree](https://prometheus.io/docs/alerting/latest/configuration/#route)
- [AlertManager Notification Templates](https://prometheus.io/docs/alerting/latest/notifications/)
- [AlertManager Inhibition](https://prometheus.io/docs/alerting/latest/configuration/#inhibit_rule)

### Integration Guides

- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [PagerDuty Events API v2](https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgw-events-api-v2-overview)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)

### Best Practices

- [Prometheus Alerting Best Practices](https://prometheus.io/docs/practices/alerting/)
- [AlertManager Architecture](https://prometheus.io/docs/alerting/latest/architecture/)
- [Alert Design Patterns](https://www.robustperception.io/how-much-should-you-alert-on/)

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-23 | 1.0.0 | Initial production-ready configuration |
| | | - Multi-channel routing (Email/Slack/PagerDuty) |
| | | - 10 receivers, 7 routes, 8 inhibition rules |
| | | - Professional HTML email templates |
| | | - Dynamic variable substitution via docker-entrypoint.sh |

---

**Maintained by**: Backend Team
**Contact**: backend-team@lia.ai
**Repository**: https://github.com/jgouviergmail/LIA-Assistant
