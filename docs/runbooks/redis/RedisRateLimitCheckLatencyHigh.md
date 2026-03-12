# Runbook: RedisRateLimitCheckLatencyHigh

**Alert Name**: `RedisRateLimitCheckLatencyHigh`
**Severity**: Critical
**Component**: Redis Rate Limiting
**Type**: Performance

---

## Description

Rate limit check latency P95 exceeds 50ms, causing significant performance degradation. Rate limiting is a synchronous operation that blocks every API request, so high latency directly impacts user experience.

**Threshold**:
- **Critical**: P95 > 50ms for 5 minutes
- **Warning**: P95 > 10ms for 10 minutes (`RedisRateLimitCheckLatencyDegraded`)

**Normal baseline**: P95 < 5ms, P99 < 10ms

---

## Impact

- **User Experience**: All API requests delayed by rate limit check overhead
- **System Health**: Cascading latency across all endpoints
- **Throughput**: Reduced requests/second capacity
- **Resource Usage**: Thread pool exhaustion if blocking

---

## Diagnosis

### 1. Check Dashboard

Navigate to **Grafana → 10 - Redis Rate Limiting** dashboard:

- **Rate Limit Check Latency P95 (ms)**: Current latency
- **Rate Limit Check Latency Distribution**: P50/P95/P99 trends
- **Redis Connection Pool Status**: Pool exhaustion?
- **Total Requests (req/s)**: Traffic spike?

### 2. Query Prometheus

```promql
# Current P95 latency by endpoint
1000 * histogram_quantile(0.95, sum(rate(redis_rate_limit_check_duration_seconds_bucket[5m])) by (le, key_prefix))

# P99 latency (worst case)
1000 * histogram_quantile(0.99, sum(rate(redis_rate_limit_check_duration_seconds_bucket[5m])) by (le))

# Connection pool utilization
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))

# Traffic volume
sum(rate(redis_rate_limit_allows_total[5m])) + sum(rate(redis_rate_limit_hits_total[5m]))
```

### 3. Check Redis Performance

```bash
# Connect to Redis
kubectl exec -it redis-0 -- redis-cli

# Check Redis stats
INFO stats
INFO clients
INFO memory

# Monitor real-time commands (sample 1 second)
MONITOR | head -100

# Check slow log
SLOWLOG GET 10

# Check Redis CPU usage
INFO cpu

# Check memory fragmentation
INFO memory | grep fragmentation_ratio
```

### 4. Network Latency Check

```bash
# Ping Redis from API pod
kubectl exec -it $(kubectl get pod -l app=lia-api -o jsonpath='{.items[0].metadata.name}') -- ping redis-service -c 10

# Check DNS resolution time
kubectl exec -it $(kubectl get pod -l app=lia-api -o jsonpath='{.items[0].metadata.name}') -- time nslookup redis-service

# Measure Redis connection latency
kubectl exec -it $(kubectl get pod -l app=lia-api -o jsonpath='{.items[0].metadata.name}') -- redis-cli -h redis-service --latency
```

---

## Root Causes

### 1. Redis Server Issues

**Symptoms:**
- High Redis CPU usage (>80%)
- Memory fragmentation >1.5
- Eviction events in Redis INFO

**Diagnosis:**
```bash
# Check Redis resource usage
kubectl top pod redis-0

# Check key count (too many keys?)
redis-cli DBSIZE

# Check memory usage breakdown
redis-cli INFO memory
```

**Resolution:**
- Increase Redis CPU/memory allocation
- Run `MEMORY PURGE` to defragment
- Clean up expired keys: `redis-cli --scan --pattern "user:*" | xargs redis-cli DEL`

### 2. Network Latency

**Symptoms:**
- High ping times (>5ms)
- Network errors in logs
- Intermittent connection failures

**Diagnosis:**
```bash
# Check pod network policies
kubectl describe networkpolicies

# Check service endpoints
kubectl get endpoints redis-service

# Measure latency histogram
redis-cli --latency-history
```

**Resolution:**
- Move Redis to same node/availability zone as API
- Check network policies blocking traffic
- Upgrade network infrastructure

### 3. Connection Pool Exhaustion

**Symptoms:**
- `redis_connection_pool_available_current` near 0
- "Connection pool exhausted" errors
- High queue times

**Diagnosis:**
```promql
# Pool utilization
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))

# Check if we're hitting max connections
redis_connection_pool_size_current
```

**Resolution:**

```python
# In apps/api/src/infrastructure/redis.py
# Increase pool size
redis_client = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    max_connections=50,  # Increase from 10
    socket_connect_timeout=5,
    socket_timeout=5,
)
```

### 4. Lua Script Performance

**Symptoms:**
- High `redis_lua_script_executions_total{status="error"}`
- Slow EVALSHA commands in MONITOR

**Diagnosis:**
```bash
# Check Lua script cache
redis-cli SCRIPT EXISTS <sha>

# Force reload script
redis-cli SCRIPT FLUSH
```

**Resolution:**
- Script will auto-reload on next request
- Optimize Lua script if bottleneck identified

### 5. Large Sliding Windows

**Symptoms:**
- `redis_sliding_window_requests_current` very high (>1000)
- Large ZCARD values

**Diagnosis:**
```promql
# Check window sizes
redis_sliding_window_requests_current

# Check specific keys
kubectl exec -it redis-0 -- redis-cli
> ZCARD user:123:contacts_search
> ZRANGE user:123:contacts_search 0 10 WITHSCORES
```

**Resolution:**
- Reduce window_seconds in rate limit config
- Reduce max_calls to limit window size
- Implement time-based key expiration

---

## Resolution Steps

### Immediate Actions (Incident Response)

#### Option 1: Scale Redis Resources

```bash
# Increase Redis CPU/memory
kubectl edit deployment redis

# Update resources
spec:
  template:
    spec:
      containers:
      - name: redis
        resources:
          requests:
            cpu: 2000m      # Was: 1000m
            memory: 4Gi     # Was: 2Gi
          limits:
            cpu: 4000m      # Was: 2000m
            memory: 8Gi     # Was: 4Gi

# Apply and restart
kubectl rollout restart deployment/redis
```

#### Option 2: Increase Connection Pool

```python
# In apps/api/src/infrastructure/redis.py
redis_client = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    max_connections=100,  # Increase
    socket_connect_timeout=10,
    socket_timeout=10,
    retry_on_timeout=True,
)
```

```bash
# Redeploy API
kubectl rollout restart deployment/lia-api
```

#### Option 3: Enable Redis Persistence Optimization

```bash
# Edit Redis config
kubectl exec -it redis-0 -- redis-cli CONFIG SET save ""

# Disable RDB snapshots temporarily (reduces I/O blocking)
# WARNING: Data loss risk if Redis crashes
```

### Short-Term Actions (1-24 hours)

1. **Optimize Lua Script**

Review `SLIDING_WINDOW_SCRIPT` in `redis_limiter.py`:
- Minimize operations
- Use efficient data structures
- Batch operations if possible

2. **Add Connection Pooling Metrics**

```python
# In metrics_redis.py
redis_connection_pool_wait_time_seconds = Histogram(
    "redis_connection_pool_wait_time_seconds",
    "Time waiting for available connection",
)
```

3. **Implement Circuit Breaker**

```python
# In redis_limiter.py
async def acquire(self, key, max_calls, window_seconds):
    try:
        # ... existing code ...
    except RedisError:
        logger.error("redis_error_circuit_open")
        # Fail open: allow request if Redis down
        return True
```

### Long-Term Actions (1-7 days)

1. **Deploy Redis Cluster**

```yaml
# redis-cluster.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cluster
spec:
  replicas: 3
  # ... cluster configuration
```

Benefits:
- Distributed load
- Higher throughput
- Fault tolerance

2. **Implement Local Caching Layer**

```python
# In redis_limiter.py
from cachetools import TTLCache

class CachedRedisRateLimiter(RedisRateLimiter):
    def __init__(self, redis):
        super().__init__(redis)
        # Cache frequent keys locally (1 second TTL)
        self._local_cache = TTLCache(maxsize=1000, ttl=1.0)

    async def acquire(self, key, max_calls, window_seconds):
        # Check local cache first
        if key in self._local_cache:
            cached_result = self._local_cache[key]
            if not cached_result["allowed"]:
                return False  # Still rate limited

        # Proceed with Redis check
        allowed = await super().acquire(key, max_calls, window_seconds)
        self._local_cache[key] = {"allowed": allowed, "timestamp": time.time()}
        return allowed
```

3. **Migrate to Dragonfly (Redis Alternative)**

[Dragonfly](https://www.dragonflydb.io/) is a drop-in Redis replacement with:
- 25x better throughput
- Lower latency (sub-millisecond P99)
- Better memory efficiency

---

## Verification

After applying fixes:

```promql
# Latency should drop below 10ms
1000 * histogram_quantile(0.95, sum(rate(redis_rate_limit_check_duration_seconds_bucket[5m])) by (le))

# Pool utilization healthy (<70%)
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current))

# No errors
sum(rate(redis_rate_limit_errors_total[5m]))
```

**Success Criteria:**
- ✅ P95 latency < 5ms sustained for 30 minutes
- ✅ P99 latency < 10ms
- ✅ Connection pool utilization < 70%
- ✅ No Redis errors or timeouts

---

## Prevention

1. **Capacity Planning**:
   - Monitor latency trends weekly
   - Scale Redis proactively before hitting limits

2. **Load Testing**:
   - Test rate limiter under peak load
   - Identify breaking points

3. **Redis Monitoring**:
   - Set up alerts for Redis CPU >70%
   - Monitor memory fragmentation
   - Track connection pool usage

4. **Optimization**:
   - Regularly review and optimize Lua scripts
   - Keep Redis version up-to-date
   - Tune Redis configuration for workload

---

## Related Alerts

- `RedisRateLimitCheckLatencyDegraded`: Warning-level latency (>10ms)
- `RedisConnectionPoolExhaustion`: Pool saturated
- `RedisRateLimitErrorsHigh`: Redis errors
- `RedisLuaScriptFailureRateHigh`: Lua script failures

---

## References

- **Code**: `apps/api/src/infrastructure/rate_limiting/redis_limiter.py`
- **Metrics**: `apps/api/src/infrastructure/observability/metrics_redis.py`
- **Redis Config**: `infrastructure/redis/redis.conf`
- **Dashboard**: Grafana → 10 - Redis Rate Limiting
- **Alerts**: `infrastructure/observability/prometheus/alerts.yml` (line 303)

---

## Escalation

**L1 Support**: Check dashboard, verify Redis health
**L2 Support**: Analyze Redis metrics, identify bottleneck
**L3 Support**: Scale resources, optimize configuration
**Engineering**: Implement architectural improvements

**On-Call Contact**: `@platform-team` in Slack #incidents channel

---

**Last Updated**: 2025-11-22
**Version**: 1.0
**Owner**: Platform Team
