# Runbook: RedisConnectionPoolExhaustion

**Alert Name**: `RedisConnectionPoolExhaustion`
**Severity**: Critical
**Component**: Redis
**Type**: Capacity

---

## Description

Redis connection pool utilization exceeds 95%, meaning the application is running out of available Redis connections. This causes requests to block/timeout while waiting for a free connection.

**Threshold**:
- **Critical**: >95% utilization for 5 minutes
- **Warning**: >80% utilization for 10 minutes (`RedisConnectionPoolHighUtilization`)

**Normal baseline**: <50% utilization

---

## Impact

- **User Experience**: API requests timeout or respond slowly
- **System Health**: Cascading failures as threads block waiting for connections
- **Availability**: Service degradation or outage if all connections exhausted
- **Resource Usage**: Thread pool exhaustion, memory pressure

---

## Diagnosis

### 1. Check Dashboard

Navigate to **Grafana → 10 - Redis Rate Limiting** dashboard:

- **Redis Connection Pool Utilization (%)**: Current pool usage
- **Redis Connection Pool Status**: Total vs Available vs In Use
- **Rate Limit Check Latency**: Likely elevated

### 2. Query Prometheus

```promql
# Current pool utilization
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))

# Pool size
redis_connection_pool_size_current

# Available connections
redis_connection_pool_available_current

# In use connections
redis_connection_pool_size_current - redis_connection_pool_available_current
```

### 3. Check Redis Server

```bash
# Connect to Redis
kubectl exec -it redis-0 -- redis-cli

# Check connected clients
INFO clients
# Output: connected_clients:XX

# List all clients
CLIENT LIST

# Check if max connections reached
CONFIG GET maxclients
```

### 4. Check Application Logs

```bash
# Look for connection pool errors
kubectl logs -l app=lia-api --tail=200 | grep -i "pool\|connection"

# Common errors:
# - "Connection pool exhausted"
# - "TimeoutError: Redis connection timeout"
# - "ConnectionError: Too many connections"
```

---

## Root Causes

### 1. Insufficient Pool Size

**Symptoms:**
- Pool utilization consistently >70%
- Traffic volume within normal range
- No connection leaks detected

**Diagnosis:**
```promql
# Check if pool size is too small for traffic
redis_connection_pool_size_current < 50
```

**Resolution:** Increase pool size (see below)

### 2. Connection Leaks

**Symptoms:**
- Pool utilization grows over time (not released)
- Available connections decrease steadily
- Requires app restart to fix

**Diagnosis:**
```bash
# Check Redis client list for old connections
kubectl exec -it redis-0 -- redis-cli CLIENT LIST | sort -k11 -n

# Look for connections open for long time (age > 3600s)
```

**Resolution:** Fix connection leak in code

### 3. Traffic Spike

**Symptoms:**
- Sudden increase in API requests
- Pool utilization spikes correspondingly
- Returns to normal when traffic subsides

**Diagnosis:**
```promql
# Check traffic volume
sum(rate(http_requests_total[5m]))

# Compare to baseline
sum(rate(http_requests_total[5m])) / sum(rate(http_requests_total[1h] offset 1d))
```

**Resolution:** Scale pool or add rate limiting

### 4. Slow Redis Operations

**Symptoms:**
- Connections held longer than expected
- High Redis latency
- Long-running operations blocking pool

**Diagnosis:**
```bash
# Check Redis slow log
kubectl exec -it redis-0 -- redis-cli SLOWLOG GET 10

# Check command stats
kubectl exec -it redis-0 -- redis-cli INFO commandstats
```

**Resolution:** Optimize slow operations

---

## Resolution Steps

### Immediate Actions (Incident Response)

#### Option 1: Increase Connection Pool Size

**Quick fix - requires deployment:**

```python
# In apps/api/src/infrastructure/redis.py
from redis.asyncio import Redis, ConnectionPool

# Current configuration
pool = ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    max_connections=10,  # TOO SMALL
    socket_connect_timeout=5,
    socket_timeout=5,
)

# UPDATED configuration
pool = ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    max_connections=100,  # INCREASED (10x)
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30,
)

redis_client = Redis(connection_pool=pool)
```

**Deployment:**
```bash
# Build and deploy
docker build -t lia-api:v1.x.x .
kubectl set image deployment/lia-api api=lia-api:v1.x.x
kubectl rollout status deployment/lia-api

# Verify pool size increased
curl http://lia-api/metrics | grep redis_connection_pool_size_current
```

#### Option 2: Restart Application (Temporary)

**⚠️ ONLY if connection leak suspected:**

```bash
# Graceful restart
kubectl rollout restart deployment/lia-api

# Monitor recovery
watch -n 2 'curl -s http://lia-api/metrics | grep redis_connection_pool'
```

#### Option 3: Scale Redis (if server-side bottleneck)

```bash
# Increase Redis max connections
kubectl exec -it redis-0 -- redis-cli CONFIG SET maxclients 10000

# Make permanent in redis.conf
kubectl edit configmap redis-config
# Add: maxclients 10000
```

### Short-Term Actions (1-24 hours)

1. **Implement Connection Pooling Best Practices**

```python
# In apps/api/src/infrastructure/redis.py
from redis.asyncio import Redis
from contextlib import asynccontextmanager

class RedisClient:
    def __init__(self):
        self.pool = ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            max_connections=100,
            # Connection lifecycle settings
            socket_keepalive=True,
            socket_keepalive_options={
                socket.TCP_KEEPIDLE: 60,
                socket.TCP_KEEPINTVL: 10,
                socket.TCP_KEEPCNT: 3,
            },
            # Health checks
            health_check_interval=30,
            # Retry logic
            retry_on_timeout=True,
            retry_on_error=[ConnectionError, TimeoutError],
        )
        self.redis = Redis(connection_pool=self.pool)

    @asynccontextmanager
    async def get_connection(self):
        """Context manager ensures connection is always returned to pool."""
        conn = None
        try:
            conn = await self.pool.get_connection("_")
            yield conn
        finally:
            if conn:
                await self.pool.release(conn)

# Usage
async def rate_limit_check(key):
    async with redis_client.get_connection() as conn:
        result = await conn.get(key)
        return result
```

2. **Add Connection Pool Monitoring**

```python
# In metrics_redis.py
redis_connection_pool_wait_time_seconds = Histogram(
    "redis_connection_pool_wait_time_seconds",
    "Time waiting for available connection from pool",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

redis_connection_pool_timeouts_total = Counter(
    "redis_connection_pool_timeouts_total",
    "Total connection pool timeout errors",
)

# In redis.py
class InstrumentedConnectionPool(ConnectionPool):
    async def get_connection(self, command_name, *keys, **options):
        start_time = time.perf_counter()
        try:
            conn = await super().get_connection(command_name, *keys, **options)
            duration = time.perf_counter() - start_time
            redis_connection_pool_wait_time_seconds.observe(duration)
            return conn
        except TimeoutError:
            redis_connection_pool_timeouts_total.inc()
            raise
```

3. **Review Code for Connection Leaks**

Common leak patterns:
```python
# ❌ BAD: Connection not returned
async def bad_pattern():
    redis = Redis(...)
    await redis.get("key")
    # Missing: await redis.close()

# ✅ GOOD: Using connection pool
async def good_pattern():
    async with redis_pool.get_connection() as conn:
        await conn.get("key")
    # Connection auto-returned to pool

# ✅ GOOD: Using singleton Redis client
async def best_pattern():
    # redis_client is global singleton with pool
    await redis_client.get("key")
```

### Long-Term Actions (1-7 days)

1. **Implement Adaptive Pool Sizing**

```python
# Auto-scale pool based on traffic
class AdaptiveConnectionPool:
    def __init__(self, min_connections=10, max_connections=200):
        self.min = min_connections
        self.max = max_connections
        self.current_size = min_connections

    async def adjust_size(self):
        utilization = self.get_utilization()
        if utilization > 0.8:
            # Scale up
            new_size = min(self.current_size * 1.5, self.max)
            await self.resize(new_size)
        elif utilization < 0.3:
            # Scale down
            new_size = max(self.current_size * 0.7, self.min)
            await self.resize(new_size)
```

2. **Deploy Redis Sentinel/Cluster**

Benefits:
- Higher connection capacity (distributed)
- Automatic failover
- Load balancing

```yaml
# redis-sentinel.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-sentinel
spec:
  replicas: 3
  serviceName: redis-sentinel
  # ... sentinel configuration
```

3. **Implement Connection Pooling Alerts**

```yaml
# In alerts.yml
- alert: RedisConnectionPoolWaitTimeHigh
  expr: |
    histogram_quantile(0.95, sum(rate(redis_connection_pool_wait_time_seconds_bucket[5m])) by (le)) > 0.1
  for: 5m
  annotations:
    summary: "High wait time for Redis connections"
    description: "P95 wait time {{ $value }}s. Pool may need scaling."
```

---

## Verification

After applying fixes:

```promql
# Pool utilization should drop below 70%
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))

# Pool size increased
redis_connection_pool_size_current >= 100

# Available connections
redis_connection_pool_available_current > 30

# No connection errors
rate(redis_connection_pool_timeouts_total[5m]) == 0
```

**Success Criteria:**
- ✅ Pool utilization < 70% sustained for 30 minutes
- ✅ Available connections > 30% of pool size
- ✅ No connection timeout errors
- ✅ Rate limit latency P95 < 10ms

---

## Prevention

1. **Capacity Planning**:
   - Right-size pool based on peak traffic
   - Formula: `max_connections = (peak_rps * avg_operation_time) * 1.5`
   - Example: `(1000 rps * 0.005s) * 1.5 = 7.5 ≈ 10 connections`

2. **Load Testing**:
   - Test connection pool under load
   - Identify breaking points
   - Validate pool size before production

3. **Code Reviews**:
   - Check for connection leaks
   - Ensure proper connection lifecycle management
   - Use connection pool patterns consistently

4. **Monitoring**:
   - Alert on >70% pool utilization (warning)
   - Track pool utilization trends
   - Monitor connection wait times

---

## Related Alerts

- `RedisConnectionPoolHighUtilization`: Warning-level (>80%)
- `RedisRateLimitCheckLatencyHigh`: Likely caused by pool exhaustion
- `RedisRateLimitErrorsHigh`: Connection errors
- `RedisDown`: Redis server unavailable

---

## References

- **Code**: `apps/api/src/infrastructure/redis.py`
- **Rate Limiter**: `apps/api/src/infrastructure/rate_limiting/redis_limiter.py`
- **Metrics**: `apps/api/src/infrastructure/observability/metrics_redis.py`
- **Dashboard**: Grafana → 10 - Redis Rate Limiting
- **Alerts**: `infrastructure/observability/prometheus/alerts.yml` (line 334)

---

## Escalation

**L1 Support**: Check dashboard, verify pool metrics
**L2 Support**: Analyze connection usage, identify leaks
**L3 Support**: Scale pool, optimize configuration
**Engineering**: Implement adaptive pooling, fix leaks

**On-Call Contact**: `@platform-team` in Slack #incidents channel

---

**Last Updated**: 2025-11-22
**Version**: 1.0
**Owner**: Platform Team
