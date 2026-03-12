# ServiceDown - Runbook

**Severity**: Critical
**Component**: API
**Impact**: Complete service outage, all user-facing functionality unavailable
**SLA Impact**: Yes - Total service unavailability

---

## 1. Alert Definition

**Alert Name**: `ServiceDown`

**PromQL Query**:
```promql
up{job="api"} == 0
```

**Thresholds**: Binary (0 = down, 1 = up)
**Duration**: For 1 minute

**Labels**:
```yaml
severity: critical
component: api
alert_type: availability
impact: total_outage
```

**Annotations**:
```yaml
summary: "API service is down"
description: "LIA API has been unreachable for more than 1 minute"
```

---

## 2. Symptoms

### What Users See
- Website/app completely inaccessible
- HTTP 502 Bad Gateway or 503 Service Unavailable
- "Cannot connect to server" errors

### What Ops See
- `up{job="api"}` = 0 in Prometheus
- API container status: `Exited` or `Restarting`
- Load balancer health checks failing
- No response on port 8000

---

## 3. Possible Causes

### Cause 1: Application Crash (High Likelihood)
**Likelihood**: High (50%)

**Verification**:
```bash
docker-compose ps api
docker-compose logs api --tail=100
```

---

### Cause 2: OOM Kill (Medium Likelihood)
**Likelihood**: Medium (30%)

**Verification**:
```bash
docker-compose logs api | grep -i "oom\|memory"
dmesg | grep -i "oom"
```

---

### Cause 3: Startup Failure (Configuration Error) (Medium Likelihood)
**Likelihood**: Medium (25%)

**Verification**:
```bash
docker-compose up api
# Watch for configuration errors during startup
```

---

## 4. Resolution Steps

### Immediate Mitigation

**Option 1: Restart API service**
```bash
docker-compose restart api

# Wait for startup
sleep 15
docker-compose ps api

# Test endpoint
curl -f http://localhost:8000/health || echo "Still down"
```

---

**Option 2: Rollback to previous version** (if recent deployment)
```bash
# Check recent commits
git log --oneline -5

# Rollback
git checkout <previous-commit>
docker-compose build api
docker-compose up -d api
```

---

## 5. Related Dashboards & Queries

**API uptime**:
```promql
up{job="api"}
```

**API restart count**:
```promql
changes(container_start_time_seconds{name="lia_api_1"}[24h])
```

---

## 6. Related Runbooks
- [ContainerDown.md](./ContainerDown.md) - General container issues
- [HighErrorRate.md](./HighErrorRate.md) - May precede complete outage

---

## 7. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
