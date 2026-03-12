# DatabaseDown - Runbook

**Severity**: Critical
**Component**: Database
**Impact**: Complete service outage, no read/write operations possible
**SLA Impact**: Yes - Total service unavailability

---

## 1. Alert Definition

**Alert Name**: `DatabaseDown`

**PromQL Query**:
```promql
up{job="postgres"} == 0
```

**Thresholds**: Binary (0 = down, 1 = up)
**Duration**: For 1 minute

**Labels**:
```yaml
severity: critical
component: database
alert_type: availability
impact: total_outage
```

**Annotations**:
```yaml
summary: "PostgreSQL database is down"
description: "PostgreSQL has been unreachable for more than 1 minute"
```

---

## 2. Symptoms

### What Users See
- Complete service outage
- "Service temporarily unavailable" (503 errors)
- All features non-functional

### What Ops See
- `up{job="postgres"}` = 0
- API logs: "Connection refused" / "Could not connect to database"
- PostgreSQL container: `Exited` or `Restarting`

---

## 3. Possible Causes

### Cause 1: PostgreSQL Crashed (High Likelihood)
**Likelihood**: High (60%)

**Verification**:
```bash
docker-compose ps postgres
docker-compose logs postgres --tail=100 | grep -i "fatal\|panic\|abort"
```

---

### Cause 2: Disk Full (Medium Likelihood)
**Likelihood**: Medium (30%)

**Verification**:
```bash
df -h /var/lib/docker
docker-compose logs postgres | grep -i "no space left"
```

---

### Cause 3: Corrupted Data Files (Low Likelihood)
**Likelihood**: Low (15%)

**Verification**:
```bash
docker-compose logs postgres | grep -i "corruption\|checksum\|invalid"
```

---

## 4. Resolution Steps

### Immediate Mitigation

**Option 1: Restart PostgreSQL**
```bash
docker-compose restart postgres

# Wait for startup
sleep 10
docker-compose ps postgres

# Test connectivity
docker-compose exec postgres pg_isready -U lia
```

---

**Option 2: Restore from backup** (if restart fails)
```bash
# Stop PostgreSQL
docker-compose down postgres

# Restore from latest backup
docker-compose exec -T postgres psql -U lia < /backups/latest.sql

# Start PostgreSQL
docker-compose up -d postgres
```

---

## 5. Related Dashboards & Queries

**Database uptime**:
```promql
up{job="postgres"}
```

---

## 6. Related Runbooks
- [CriticalDatabaseConnections.md](./CriticalDatabaseConnections.md) - Connection pool issues
- [DiskSpaceCritical.md](./DiskSpaceCritical.md) - May cause database crash

---

## 7. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
