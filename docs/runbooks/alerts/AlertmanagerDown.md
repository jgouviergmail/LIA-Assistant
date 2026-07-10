# AlertmanagerDown - Runbook

**Severity**: critical
**Component**: observability
**Impact**: The alerting chain itself is broken: Prometheus keeps evaluating rules but **no email leaves the box**. Every other alert in this directory is silent while this fires.
**SLA Impact**: No direct user impact — MTTR impact on every other incident.

---

## 1. Alert Definition

**Alert Name**: `AlertmanagerDown`

**Prometheus Expression**:
```promql
up{job="alertmanager"} == 0
```

**Firing Duration**: `for: 5m`

**Labels**: `severity: critical`, `component: observability`, `tier: core`

**Detection caveat (assumed limitation, ADR-119)**: this alert cannot email you — Alertmanager is the mailer. It is visible in the Prometheus UI (`/alerts`), in Grafana, and indirectly in the logwatch daily digest (Alertmanager notify errors in Prometheus logs). An external dead-man's-switch (e.g. healthchecks.io watchdog) is the documented future hardening.

---

## 2. Symptoms

### What Ops See
- Prometheus UI shows the alert firing; `docker ps` shows the alertmanager container missing/restarting.
- Prometheus logs: `Error sending alert ... connection refused ... alertmanager:9093`.

---

## 3. Possible Causes

### Cause 1: Config rendering failed at startup (High Likelihood after env changes)
The entrypoint renders the config from env vars. Missing SMTP variables fall back to a log-only config (by design); a malformed template kills the container.
```bash
docker logs lia-alertmanager-prod 2>&1 | head -30
# Look for "AlertManager Configuration Rendering" banner and which mode was selected:
# "Mode: Email only" is correct for production; "minimal log-only" means SMTP vars are missing.
```

### Cause 2: Container OOM / stopped (Medium Likelihood)
```bash
docker ps -a --filter name=alertmanager
docker inspect lia-alertmanager-prod --format '{{.State.ExitCode}} {{.State.OOMKilled}}'
```

---

## 4. Resolution Steps

### Immediate
```bash
docker restart lia-alertmanager-prod
docker logs lia-alertmanager-prod 2>&1 | grep -E "Mode:|Listening"
```

### Verify the chain end-to-end (after any Alertmanager incident)
```bash
# Inject a synthetic alert and confirm the email arrives:
docker exec lia-alertmanager-prod amtool alert add TestAlert severity=warning \
  --annotation=summary="Manual chain test" --alertmanager.url=http://localhost:9093
```

### Post-Recovery Verification
- `up{job="alertmanager"} == 1`; the synthetic alert email arrived.
