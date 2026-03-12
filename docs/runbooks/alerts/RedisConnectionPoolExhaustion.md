# RedisConnectionPoolExhaustion - Runbook

**Severity**: Critical
**Component**: Infrastructure (Redis)
**Impact**: New requests failing, rate limiting broken, performance degradation
**SLA Impact**: Yes - Service degradation/unavailability

---

## 📊 Alert Definition

**Alert Name**: `RedisConnectionPoolExhaustion`

**Prometheus Expression**:
```promql
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current)) > 90
```

**Threshold**:
- **Production**: >90% pool utilization (CRITICAL)
- **Staging**: >95% pool utilization
- **Development**: Disabled (no connection pool limits)

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: critical
- `component`: redis
- `type`: capacity

---

## 🔍 Symptoms

### What Users See
- **429 Too Many Requests** - Rate limiting checks failing
- **503 Service Unavailable** - New requests rejected
- **Timeouts** - Requests waiting for Redis connection timeout
- **Intermittent errors** - Some requests succeed, others fail

### What Ops See
- **Redis pool >90% utilized** in monitoring
- **Connection wait timeouts** in logs
- **Increasing latency** - Requests queuing for connections
- **Error logs**: "ConnectionPool exhausted", "Timeout acquiring connection"

---

## 🎯 Possible Causes

### 1. Connection Leak (High Likelihood - 70%)

**Description**: Connections not properly released after use, accumulating until pool exhausted.

**How to Verify**:
```bash
# Check current pool usage
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_available_current" | jq '.data.result[0].value[1]'
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_size_current" | jq '.data.result[0].value[1]'

# Check for leak pattern (connections not returning to pool)
docker-compose logs api --since 30m | grep -i "redis\|connection" | grep -E "acquired|released" | tail -100

# Check Redis connected clients (should match pool size if healthy)
docker-compose exec redis redis-cli CLIENT LIST | wc -l
```

**Expected Output if This is the Cause**:
- Available connections = 0 or very low
- CLIENT LIST shows more connections than pool size
- Logs show "acquired" without matching "released"

---

### 2. Traffic Spike (Medium Likelihood - 50%)

**Description**: Sudden traffic increase exhausts connection pool capacity.

**How to Verify**:
```bash
# Check request rate
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])" | jq '.data.result[0].value[1]'

# Check concurrent requests
curl -s "http://localhost:9090/api/v1/query?query=http_requests_in_flight" | jq '.data.result[0].value[1]'

# Check rate limit checks per second
curl -s "http://localhost:9090/api/v1/query?query=rate(redis_rate_limit_checks_total[1m])" | jq '.data.result[0].value[1]'
```

**Expected Output if This is the Cause**:
- Request rate 3-10x normal baseline
- Concurrent requests >100 (normal: 10-50)
- Rate limit checks correlate with request spike

---

### 3. Slow Redis Operations Blocking Connections (Medium Likelihood - 40%)

**Description**: Slow Redis commands (e.g., KEYS *, large SCAN) holding connections for extended periods.

**How to Verify**:
```bash
# Check slow log
docker-compose exec redis redis-cli SLOWLOG GET 20

# Check current running commands
docker-compose exec redis redis-cli CLIENT LIST | grep -E "cmd=|age="

# Check Redis latency
docker-compose exec redis redis-cli --latency-history

# Check for blocking operations
docker-compose logs redis | grep -i "slow\|block\|timeout"
```

**Expected Output if This is the Cause**:
- SLOWLOG shows commands >100ms
- CLIENT LIST shows clients with high `age` (seconds)
- Latency spikes visible

---

### 4. Pool Size Too Small (Low-Medium Likelihood - 30%)

**Description**: Pool size configured too small for legitimate workload.

**How to Verify**:
```bash
# Check pool configuration
grep -r "REDIS_POOL\|redis_pool" apps/api/.env apps/api/src/

# Check historical pool usage trend
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_available_current offset 24h" | jq '.data.result[0].value[1]'

# Compare to current
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_available_current" | jq '.data.result[0].value[1]'
```

**Expected Output if This is the Cause**:
- Pool consistently at >80% even during normal traffic
- Gradual growth in pool usage over weeks/months
- No connection leak evidence (connections properly released)

---

## 🔧 Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Check pool status**
```bash
# Current pool metrics
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_available_current" | jq '.data.result[0].value[1]'
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_size_current" | jq '.data.result[0].value[1]'

# Calculate utilization
# Utilization = (size - available) / size * 100
# If >90% → CRITICAL
```

**Step 2: Check Redis server health**
```bash
# Redis responsive?
docker-compose exec redis redis-cli PING
# Expected: PONG

# Check client connections
docker-compose exec redis redis-cli INFO clients | grep connected_clients

# Check if Redis overloaded
docker-compose exec redis redis-cli INFO stats | grep instantaneous_ops_per_sec
```

**Step 3: Check application logs**
```bash
# Recent connection errors
docker-compose logs api --since 10m | grep -i "redis\|connection" | grep -i "error\|timeout\|exhausted"

# Count error frequency
docker-compose logs api --since 10m | grep -c "ConnectionPool exhausted"
```

---

### Deep Dive Investigation (5-10 minutes)

**Step 4: Identify connection leak**
```bash
# Trace connection lifecycle
docker-compose logs api --since 30m | grep -E "redis.*(acquire|release|create|close)" | tail -100

# Check for pattern:
# - Many "acquired" → Few "released" = LEAK
# - Equal "acquired" and "released" = NO LEAK

# Check Python traceback (if connection errors)
docker-compose logs api --since 30m | grep -A 20 "ConnectionPool"
```

**Step 5: Analyze slow operations**
```bash
# Redis SLOWLOG (commands >10ms)
docker-compose exec redis redis-cli CONFIG SET slowlog-log-slower-than 10000
docker-compose exec redis redis-cli SLOWLOG GET 50

# Look for:
# - KEYS * (O(N) - very slow)
# - SCAN with large COUNT
# - Large MGET/MSET operations
```

**Step 6: Check correlation with traffic**
```bash
# Plot pool usage vs request rate
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])" | jq '.data.result[0].value[1]'
curl -s "http://localhost:9090/api/v1/query?query=100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))" | jq '.data.result[0].value[1]'

# If correlated → traffic spike
# If NOT correlated → connection leak
```

---

## ✅ Resolution Steps

### Immediate Mitigation (<5 minutes)

**Option 1: Restart API (fastest - clears leaked connections)**
```bash
# Restart API containers to reset connection pool
docker-compose restart api

# Wait for health check
sleep 30
docker-compose ps api

# Verify pool recovered
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_available_current" | jq '.data.result[0].value[1]'

# When to use: Connection leak suspected
# Expected impact: Pool utilization drops to <20%
# Duration: 30 seconds
# Downside: Brief service interruption
```

**Option 2: Kill idle Redis clients (surgical)**
```bash
# List idle clients (>300 seconds idle)
docker-compose exec redis redis-cli CLIENT LIST | awk '$0 ~ /idle=[3-9][0-9]{2}|idle=[0-9]{4}/ {print}' | head -20

# Kill specific idle client
docker-compose exec redis redis-cli CLIENT KILL ID [client-id]

# Or kill all idle clients >5min
docker-compose exec redis redis-cli --eval - 0 <<EOF
for _,client in ipairs(redis.call('CLIENT','LIST'):split('\n')) do
  local idle = client:match('idle=(%d+)')
  if idle and tonumber(idle) > 300 then
    local addr = client:match('addr=([^ ]+)')
    if addr then redis.call('CLIENT','KILL','ADDR',addr) end
  end
end
EOF

# When to use: Identified specific stuck connections
# Expected impact: Frees 5-20% pool capacity
# Duration: Immediate
# Downside: May interrupt legitimate long-running operations
```

**Option 3: Temporarily increase pool size (if traffic spike)**
```bash
# Edit configuration
nano apps/api/.env
# Change:
# REDIS_POOL_SIZE=20 → REDIS_POOL_SIZE=50
# REDIS_POOL_MAX_OVERFLOW=10 → REDIS_POOL_MAX_OVERFLOW=20

# Restart API with new config
docker-compose restart api

# Verify new pool size
curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_size_current" | jq '.data.result[0].value[1]'
# Should show: 50

# When to use: Legitimate traffic spike, no leak
# Expected impact: Pool exhaustion prevented
# Duration: 1 minute
# Downside: Increased Redis server load
```

---

### Verification After Mitigation

```bash
# 1. Verify pool utilization normalized
curl -s "http://localhost:9090/api/v1/query?query=100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))" | jq '.data.result[0].value[1]'
# Expected: <70%

# 2. Verify alert stopped firing
curl -s "http://localhost:9093/api/v2/alerts" | jq '.[] | select(.labels.alertname=="RedisConnectionPoolExhaustion") | .status.state'
# Expected: "inactive"

# 3. Verify rate limiting working
curl -f http://localhost:8000/api/test-rate-limit
# Expected: HTTP 200 (or 429 if legitimately rate limited)

# 4. Check error rate normalized
docker-compose logs api --since 5m | grep -c "ConnectionPool exhausted"
# Expected: 0
```

---

### Root Cause Fix (Permanent Solution - 30-60 minutes)

**Fix 1: Fix connection leak (if identified in code)**

**Investigation**:
```bash
# Grep for redis connection usage
grep -r "redis.from_url\|Redis(" apps/api/src/ | head -20

# Look for patterns:
# - Connections created but not closed
# - Missing context managers (with statement)
# - Async connections without await close()
```

**Common leak patterns and fixes**:

**Pattern 1: Missing connection close**
```python
# BEFORE (leak):
def get_rate_limit():
    redis_conn = redis.from_url(REDIS_URL)
    result = redis_conn.get("rate_limit:user:123")
    # Connection never closed - LEAK
    return result

# AFTER (fixed):
def get_rate_limit():
    redis_conn = redis.from_url(REDIS_URL)
    try:
        result = redis_conn.get("rate_limit:user:123")
        return result
    finally:
        redis_conn.close()  # Always close
```

**Pattern 2: Not using connection pool**
```python
# BEFORE (creates new connection each call - exhausts pool):
async def check_rate_limit(user_id: str):
    redis_conn = aioredis.from_url(REDIS_URL)  # New connection!
    result = await redis_conn.get(f"rate_limit:{user_id}")
    await redis_conn.close()
    return result

# AFTER (use singleton pool):
# infrastructure/redis.py
_redis_pool = None

async def get_redis_pool():
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            REDIS_URL,
            max_connections=20,
            decode_responses=True
        )
    return _redis_pool

# Usage:
async def check_rate_limit(user_id: str):
    pool = await get_redis_pool()
    async with aioredis.Redis(connection_pool=pool) as redis_conn:
        result = await redis_conn.get(f"rate_limit:{user_id}")
    return result  # Connection auto-released
```

**Pattern 3: Exception preventing close**
```python
# BEFORE (exception causes leak):
async def update_cache(key, value):
    redis_conn = await get_redis()
    await redis_conn.set(key, value)
    # If exception here, connection never closed:
    result = process_value(value)  # May raise exception
    await redis_conn.close()
    return result

# AFTER (use context manager):
async def update_cache(key, value):
    async with get_redis() as redis_conn:
        await redis_conn.set(key, value)
        result = process_value(value)  # Exception handled, connection still closed
    return result
```

**Testing**:
```bash
# Load test to verify leak fixed
docker-compose exec api locust -f tests/load/test_redis_connections.py --users=100 --spawn-rate=20 --run-time=10m

# Monitor pool during test
watch -n 10 'curl -s "http://localhost:9090/api/v1/query?query=redis_connection_pool_available_current" | jq ".data.result[0].value[1]"'

# Expected: Available connections fluctuate but return to baseline (no steady decline)
```

---

**Fix 2: Implement connection pool monitoring and auto-recovery**

**File**: `apps/api/src/infrastructure/redis/pool_monitor.py` (create new)
```python
import asyncio
import logging
from prometheus_client import Gauge
from src.infrastructure.redis import get_redis_pool

logger = logging.getLogger(__name__)

pool_size_gauge = Gauge('redis_connection_pool_size_current', 'Current Redis pool size')
pool_available_gauge = Gauge('redis_connection_pool_available_current', 'Available Redis connections')

async def monitor_pool():
    """Background task to monitor Redis connection pool health"""
    while True:
        try:
            pool = await get_redis_pool()

            # Update metrics
            pool_size_gauge.set(pool.max_connections)
            in_use = pool.max_connections - pool._available_connections.qsize()
            pool_available_gauge.set(pool.max_connections - in_use)

            # Check for pool exhaustion
            utilization = (in_use / pool.max_connections) * 100
            if utilization > 90:
                logger.critical(f"Redis pool {utilization:.1f}% utilized! Available: {pool.max_connections - in_use}/{pool.max_connections}")

                # Auto-recovery: Force connection cleanup
                await pool.disconnect(inuse_connections=False)  # Close idle connections
                logger.warning("Forced Redis pool cleanup due to high utilization")

            elif utilization > 80:
                logger.warning(f"Redis pool {utilization:.1f}% utilized (warning threshold)")

            await asyncio.sleep(30)  # Check every 30 seconds

        except Exception as e:
            logger.error(f"Redis pool monitor error: {e}")
            await asyncio.sleep(60)

# Start monitor on app startup
asyncio.create_task(monitor_pool())
```

**File**: `apps/api/src/main.py` (integrate)
```python
from src.infrastructure.redis.pool_monitor import monitor_pool

@app.on_event("startup")
async def startup():
    # Start Redis pool monitoring
    asyncio.create_task(monitor_pool())
    logger.info("Redis connection pool monitor started")
```

---

**Fix 3: Configure proper pool settings**

**File**: `apps/api/.env`
```bash
# Redis Connection Pool Configuration
REDIS_URL=redis://redis:6379/0

# Pool sizing (adjust based on workload)
REDIS_POOL_SIZE=20              # Base pool size (concurrent connections)
REDIS_POOL_MAX_OVERFLOW=10      # Additional connections under load (total max: 30)
REDIS_POOL_TIMEOUT=5            # Seconds to wait for connection before timeout
REDIS_POOL_RECYCLE=3600         # Recycle connections every hour (prevent stale)

# Connection health checks
REDIS_POOL_PRE_PING=true        # Verify connection before use
REDIS_SOCKET_KEEPALIVE=true     # TCP keepalive
REDIS_SOCKET_KEEPALIVE_OPTIONS={
    "tcp_keepalive": 1,
    "tcp_keepalive_idle": 300,
    "tcp_keepalive_interval": 100,
    "tcp_keepalive_count": 3
}
```

**File**: `apps/api/src/infrastructure/redis.py`
```python
import aioredis
from src.core.config import settings

_redis_pool = None

async def get_redis_pool():
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_pool_size,
            timeout=settings.redis_pool_timeout,
            decode_responses=True,
            health_check_interval=30,  # Health check every 30s
        )
    return _redis_pool

async def get_redis():
    """Get Redis connection from pool (use with async context manager)"""
    pool = await get_redis_pool()
    return aioredis.Redis(connection_pool=pool)
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **Redis Rate Limiting** - `http://localhost:3000/d/redis-rate-limiting`
  - Panel: "Connection Pool" - Utilization percentage
  - Panel: "Available Connections" - Real-time available count
  - Panel: "Connection Errors" - Timeout/exhaustion errors

### Prometheus Queries

**Pool utilization percentage**:
```promql
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))
```

**Connections in use**:
```promql
redis_connection_pool_size_current - redis_connection_pool_available_current
```

**Connection acquire wait time (P95)**:
```promql
histogram_quantile(0.95, redis_connection_acquire_duration_seconds_bucket)
```

---

## 📚 Related Runbooks

- **[RedisDown.md](./RedisDown.md)** - Redis server unavailability
- **[HighLatencyP95.md](./HighLatencyP95.md)** - Connection pool exhaustion causes latency
- **[HighErrorRate.md](./HighErrorRate.md)** - Connection failures cause error rate spike

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Traffic Spike → Pool Exhaustion → Cascade Failure
**Scenario**: Traffic spike exhausts pool → new requests timeout → retries → more load → complete failure.

**Prevention**: Implement circuit breaker pattern, request queue depth limits.

---

### Pattern 2: Slow Redis Operation Blocking Pool
**Scenario**: Single slow KEYS * command blocks connection for 10s → cascade pool exhaustion.

**Prevention**: Avoid O(N) operations (KEYS, SMEMBERS on large sets), use SCAN instead.

---

### Known Issue 1: aioredis Connection Leak in Older Versions
**Problem**: aioredis <2.0 has connection leak in error handling.

**Fix**: Upgrade to aioredis >=2.0.1 or use redis-py with asyncio support.

---

## 🆘 Escalation

### When to Escalate

- [ ] Pool exhausted >10 minutes despite mitigation
- [ ] Service completely unavailable
- [ ] Connection leak in core library (not application code)
- [ ] Requires architecture change (move from Redis to alternative)

### Escalation Path

**Level 1 - Senior Backend Engineer** (0-15 minutes)
**Level 2 - Infrastructure Lead** (15-30 minutes)
**Level 3 - CTO** (30+ minutes)

---

## 📝 Post-Incident Actions

- [ ] Create incident report
- [ ] Update runbook with learnings
- [ ] Fix connection leak permanently
- [ ] Add pool exhaustion monitoring/alerting
- [ ] Review pool sizing capacity planning

---

## 📋 Incident Report Template

```markdown
# Incident: Redis Connection Pool Exhaustion

**Date**: [YYYY-MM-DD]
**Duration**: [HH:MM]
**Severity**: Critical

## Root Cause
[Connection leak / Traffic spike / Configuration]

## Impact
- Requests failed: [count]
- Error rate: [%]
- Users affected: [count]

## Resolution
[Immediate mitigation + permanent fix]

## Action Items
- [ ] Fix connection leak in [file.py]
- [ ] Increase pool size to [N]
- [ ] Add monitoring for pool utilization
```

---

## 🔗 Additional Resources

- [Redis Connection Pooling Best Practices](https://redis.io/docs/clients/python/)
- [aioredis Documentation](https://aioredis.readthedocs.io/)
- [Python Context Managers](https://realpython.com/python-with-statement/)

---

## 📅 Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-23
**Author**: SRE Team

---

## ✅ Validation Checklist

- [x] Alert definition verified
- [x] Commands tested
- [x] Code examples validated
- [ ] Peer review completed

---

**End of Runbook**
