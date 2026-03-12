# HighDatabaseConnections - Runbook

**Severity**: Warning
**Component**: Database
**Impact**: Early warning before pool exhaustion, no immediate user impact
**SLA Impact**: No - Preventive alert

---

## 1. Alert Definition

**Alert Name**: `HighDatabaseConnections`

**PromQL Query**:
```promql
(sqlalchemy_pool_connections{state="busy"} / sqlalchemy_pool_connections{state="total"}) * 100 > <<<ALERT_DATABASE_CONNECTIONS_HIGH_PERCENT>>>
```

**Thresholds**:
- **Production**: >70% pool utilization (Warning - early alert before critical)
- **Staging**: >80%
- **Development**: >85%

**Duration**: For 5 minutes

**Labels**:
```yaml
severity: warning
component: database
alert_type: resource_utilization
impact: preventive
```

**Annotations**:
```yaml
summary: "Database connection pool high: {{ $value }}%"
description: "Connection pool at {{ $value }}% utilization (threshold: <<<ALERT_DATABASE_CONNECTIONS_HIGH_PERCENT>>>%)"
```

---

## 2. Symptoms

### What Users See
- No visible impact yet (preventive alert)
- Slightly slower response times (if connections queueing)

### What Ops See
- Connection pool metrics showing >70% utilization
- Potential queue forming for database connections
- Warning that critical threshold (85%) approaching

---

## 3. Possible Causes

### Cause 1: Traffic Increase (High Likelihood)
**Likelihood**: High (50%)

**Verification**:
```bash
# Check request rate trend
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total[5m]))" | jq '.data.result[0].value[1]'

# Compare to 24h ago
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total[5m] offset 24h))" | jq '.data.result[0].value[1]'
```

---

### Cause 2: Slow Queries Holding Connections Longer (Medium Likelihood)
**Likelihood**: Medium (30%)

**Verification**:
```bash
# Check query duration
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  now() - query_start AS duration,
  state,
  substring(query, 1, 100) AS query
FROM pg_stat_activity
WHERE datname = 'lia'
  AND state != 'idle'
ORDER BY duration DESC;
"
```

---

### Cause 3: Connection Leaks (Low-Medium Likelihood)
**Likelihood**: Low-Medium (20%)

**Verification**:
```bash
# Check for idle connections
docker-compose exec postgres psql -U lia -c "
SELECT state, COUNT(*) FROM pg_stat_activity
WHERE datname = 'lia'
GROUP BY state;
"

# High "idle in transaction" indicates leaks
```

---

## 4. Resolution Steps

### Immediate Mitigation

**Option 1: Increase connection pool size**

**File**: `apps/api/.env`
```bash
# Increase from 20 to 30
DATABASE_POOL_SIZE=30
DATABASE_MAX_OVERFLOW=10
```

**Restart**:
```bash
docker-compose restart api
```

---

**Option 2: Kill idle connections**

```bash
# Kill connections idle >5 minutes
docker-compose exec postgres psql -U lia -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'lia'
  AND state = 'idle'
  AND state_change < NOW() - INTERVAL '5 minutes';
"
```

---

### Root Cause Fix

**Fix 1: Implement connection pooling best practices**

**File**: `apps/api/src/infrastructure/database/session.py`
```python
from sqlalchemy.pool import QueuePool

engine = create_async_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True,  # Verify connections before use
)
```

---

**Fix 2: Use context managers to ensure connection cleanup**

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_session():
    """Ensure connections always released"""
    session = async_sessionmaker(engine)()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()  # CRITICAL: Always close

# Usage
async with get_db_session() as session:
    result = await session.execute(query)
```

---

## 5. Related Dashboards & Queries

**Connection pool utilization**:
```promql
(sqlalchemy_pool_connections{state="busy"} / sqlalchemy_pool_connections{state="total"}) * 100
```

---

## 6. Related Runbooks
- [CriticalDatabaseConnections.md](./CriticalDatabaseConnections.md) - Critical threshold (>85%)
- [CheckpointSaveSlowCritical.md](./CheckpointSaveSlowCritical.md) - Slow queries

---

## 7. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
