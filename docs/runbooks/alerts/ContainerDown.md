# ContainerDown - Runbook

**Severity**: Critical
**Component**: Infrastructure
**Impact**: Service component offline, reduced functionality or complete outage
**SLA Impact**: Yes - Service availability affected

---

## 1. Alert Definition

**Alert Name**: `ContainerDown`

**PromQL Query**:
```promql
up{job=~"api|postgres|redis|prometheus|grafana|alertmanager"} == 0
```

**Thresholds**: Binary (0 = down, 1 = up)

**Duration**: For 1 minute

**Labels**:
```yaml
severity: critical
component: infrastructure
alert_type: availability
impact: service_down
```

**Annotations**:
```yaml
summary: "Container {{ $labels.job }} is down on {{ $labels.instance }}"
description: "Container {{ $labels.job }} has been down for more than 1 minute"
```

---

## 2. Symptoms

### What Users See
- **API down** (`api` container): Complete service outage, HTTP 502/503 errors
- **Database down** (`postgres` container): Service outage, "database connection failed"
- **Redis down** (`redis` container): Degraded performance, rate limiting disabled
- **Monitoring down** (`prometheus/grafana` containers): No visibility, alerts may not fire

### What Ops See
- Container status shows `Exited` or `Restarting` in `docker-compose ps`
- Prometheus target shows "DOWN" in targets page
- Container restart count increasing
- Health check failures in logs

---

## 3. Possible Causes

### Cause 1: Application Crash / Unhandled Exception (High Likelihood)
**Description**: Application code encountered fatal error (OOM, unhandled exception, panic).

**Likelihood**: High (50%) - Most common in production

**Verification**:
```bash
# Check container status and restart count
docker-compose ps

# Check exit code and last logs
docker-compose logs --tail=100 [service]

# Look for specific crash indicators
docker-compose logs [service] | grep -i "error\|exception\|fatal\|panic\|segfault\|oom"

# Check container inspect for exit code
docker inspect lia_[service]_1 | jq '.[0].State'
```

**Expected Output**:
- Exit code 137: OOM killed
- Exit code 1: Application error
- Exit code 139: Segmentation fault

---

### Cause 2: Resource Exhaustion (Memory/CPU) (Medium-High Likelihood)
**Description**: Container exceeded resource limits or host resources depleted.

**Likelihood**: Medium-High (40%)

**Verification**:
```bash
# Check container resource usage
docker stats --no-stream

# Check resource limits
docker inspect lia_[service]_1 | jq '.[0].HostConfig.Memory'
docker inspect lia_[service]_1 | jq '.[0].HostConfig.NanoCpus'

# Check OOM kills
dmesg | grep -i "oom"
docker-compose logs [service] | grep -i "oom\|memory"

# Check host resources
free -h
top -b -n 1 | head -20
```

---

### Cause 3: Configuration Error / Invalid Environment Variables (Medium Likelihood)
**Description**: Recent config change caused container to fail at startup.

**Likelihood**: Medium (30%) - Common after deployments

**Verification**:
```bash
# Check recent configuration changes
git log --since="24 hours ago" --oneline -- apps/api/.env docker-compose.yml

# Try starting container manually with verbose logging
docker-compose up [service]

# Check environment variables
docker-compose config | grep -A 20 "[service]:"

# Validate environment file
cat apps/api/.env | grep -v "^#" | grep "="
```

---

### Cause 4: Dependency Failure (Database/Redis Unavailable) (Medium Likelihood)
**Description**: Container depends on another service that's unavailable at startup.

**Likelihood**: Medium (25%) - Especially during multi-service restarts

**Verification**:
```bash
# Check dependency chain
docker-compose config | grep "depends_on" -A 5

# Check if dependencies are running
docker-compose ps postgres redis

# Check connection from failing container
docker-compose run --rm [service] nc -zv postgres 5432
docker-compose run --rm [service] nc -zv redis 6379

# Check database availability
docker-compose exec postgres pg_isready -U lia
```

---

## 4. Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Identify which container is down**
```bash
docker-compose ps

# Look for status:
# - "Exited (1)" = Crashed
# - "Restarting" = Crash loop
# - "Up (unhealthy)" = Health check failing
```

**Step 2: Check recent logs**
```bash
docker-compose logs --tail=50 [service]

# Look for last message before crash
# Common patterns:
# - "Connection refused" → Dependency issue
# - "Out of memory" → Resource exhaustion
# - "Port already in use" → Port conflict
# - "Config error" → Configuration issue
```

**Step 3: Attempt restart**
```bash
# Quick restart
docker-compose restart [service]

# Wait 30 seconds and check status
sleep 30
docker-compose ps [service]
```

---

### Deep Dive Analysis (5-10 minutes)

**Step 4: Analyze exit code and state**
```bash
# Get detailed state
docker inspect lia_[service]_1 | jq '.[0].State'

# Exit codes:
# 0 = Normal exit (should auto-restart)
# 1 = Application error
# 137 = SIGKILL (OOM)
# 139 = SIGSEGV (segfault)
# 143 = SIGTERM (graceful shutdown)
```

**Step 5: Check resource constraints**
```bash
# Memory usage history
docker stats lia_[service]_1 --no-stream

# Host memory pressure
free -h
cat /proc/meminfo | grep -i available

# Disk space (can prevent container start)
df -h /var/lib/docker
```

**Step 6: Validate configuration**
```bash
# Test docker-compose configuration
docker-compose config

# Validate service-specific config
docker-compose run --rm [service] [validation-command]
# Examples:
# API: python -c "from src.core.config import settings; print('OK')"
# PostgreSQL: postgres --version
```

**Step 7: Check network connectivity**
```bash
# Verify network exists
docker network ls | grep lia

# Check DNS resolution
docker-compose run --rm [service] nslookup postgres
docker-compose run --rm [service] ping -c 3 redis
```

---

## 5. Resolution Steps

### Immediate Mitigation (<2 minutes)

**Option 1: Restart container (Fastest - 30 seconds)**
```bash
# Restart specific service
docker-compose restart [service]

# Verify status
docker-compose ps [service]

# Watch logs for successful startup
docker-compose logs -f [service]

# When to use: Transient failure, no obvious root cause
```

**Option 2: Recreate container (Fast - 1 minute)**
```bash
# Stop and remove container
docker-compose down [service]

# Recreate from scratch
docker-compose up -d [service]

# Verify
docker-compose ps [service]

# When to use: Configuration changes, volume corruption
```

**Option 3: Restart all services (Medium - 2 minutes)**
```bash
# Graceful restart all
docker-compose restart

# Or hard restart
docker-compose down && docker-compose up -d

# Verify all services
docker-compose ps

# When to use: Multiple services down, dependency issues
```

---

### Root Cause Fix (10-30 minutes)

**Fix 1: Address OOM (Memory Limit Too Low)**

**Update docker-compose.yml**:
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G  # Increase from 1G
        reservations:
          memory: 1G
```

**Apply**:
```bash
docker-compose up -d api
```

**Verify**:
```bash
docker stats --no-stream lia_api_1
```

---

**Fix 2: Fix Configuration Error**

**Validate environment variables**:
```bash
# Check for missing required vars
cat apps/api/.env.example | grep -v "^#" | cut -d= -f1 | while read var; do
  grep -q "^$var=" apps/api/.env || echo "Missing: $var"
done
```

**Test configuration**:
```bash
# Dry-run with config validation
docker-compose run --rm api python -c "
from src.core.config import settings
print('Database URL:', settings.database_url)
print('Redis URL:', settings.redis_url)
print('LLM Provider:', settings.llm_provider)
"
```

**Apply fix and restart**:
```bash
# Edit .env file
nano apps/api/.env

# Restart with new config
docker-compose up -d api
```

---

**Fix 3: Add Health Checks and Restart Policies**

**Update docker-compose.yml**:
```yaml
services:
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lia"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
```

**Apply**:
```bash
docker-compose up -d
```

---

**Fix 4: Implement Graceful Shutdown**

**For API (FastAPI)**:

**File**: `apps/api/src/main.py`
```python
import signal
import sys

def signal_handler(sig, frame):
    logger.info("Received shutdown signal, gracefully shutting down...")
    # Close database connections
    from src.infrastructure.database import engine
    engine.dispose()
    # Close Redis connections
    # ... close other resources
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
```

**Update Dockerfile**:
```dockerfile
# Use exec form to properly handle signals
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 6. Related Dashboards & Queries

### Grafana Dashboards
- **Infrastructure Overview** - `http://localhost:3000/d/infrastructure-overview`
  - Panel: "Container Status" - All services up/down
  - Panel: "Container Restarts" - Restart count over time

### Prometheus Queries

**Container uptime**:
```promql
up{job=~"api|postgres|redis"}
```

**Container restart count (last 24h)**:
```promql
changes(container_start_time_seconds{name=~"lia.*"}[24h])
```

**Time since last restart**:
```promql
time() - container_start_time_seconds{name=~"lia.*"}
```

---

## 7. Related Runbooks
- [ServiceDown.md](./ServiceDown.md) - Higher-level service unavailability
- [DatabaseDown.md](./DatabaseDown.md) - Specific PostgreSQL issues
- [HighErrorRate.md](./HighErrorRate.md) - May precede container crash

---

## 8. Common Patterns & Known Issues

### Pattern 1: Database Migration Failure at Startup
**Scenario**: API container crashes on startup during Alembic migration.

**Detection**:
```bash
docker-compose logs api | grep -i "alembic\|migration"
```

**Fix**: Run migrations manually first:
```bash
docker-compose run --rm api alembic upgrade head
docker-compose up -d api
```

---

### Pattern 2: Redis Connection Timeout During Traffic Spike
**Scenario**: API crashes when Redis is slow/unavailable during high load.

**Prevention**: Implement connection retry with circuit breaker (see LLMAPIFailureRateHigh.md pattern).

---

## 9. Escalation

### When to Escalate
- Container crashes repeatedly (>5 times in 10 minutes)
- Root cause unclear after 15 minutes investigation
- Multiple containers down simultaneously
- Data corruption suspected

### Escalation Path
1. **Level 1 - Senior SRE** (0-15 minutes)
2. **Level 2 - Infrastructure Lead** (15-30 minutes)
3. **Level 3 - CTO** (30+ minutes)

---

## 10. Post-Incident Actions

### Immediate (<1 hour)
- [ ] Create incident report
- [ ] Document root cause

### Short-term (<24 hours)
- [ ] Add missing health checks
- [ ] Review resource limits
- [ ] Update monitoring

---

## 11. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team

---

## 12. Validation Checklist

- [x] Alert definition verified
- [x] Commands tested
- [x] Resolution steps validated
- [ ] Peer review completed
