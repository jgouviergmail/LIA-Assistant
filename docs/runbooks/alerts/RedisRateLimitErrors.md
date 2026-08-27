# Runbook: RedisRateLimitErrors

**Alert Name**: `RedisRateLimitErrorsHigh`
**Severity**: Critical
**Component**: Redis Rate Limiting
**Type**: Reliability

---

## Description

Redis rate limiting operations are failing at a high rate (>10 errors/second), indicating a systemic issue with the rate limiting infrastructure. The application fails open (allows requests) to maintain availability, but rate limiting protection is compromised.

**Threshold**:
- **Critical**: >10 errors/second for 3 minutes
- **Warning**: >1 error/second for 10 minutes (`RedisRateLimitErrorsDetected`)

**Normal baseline**: 0 errors

---

## Impact

- **Security**: Rate limiting bypassed, vulnerable to abuse
- **User Experience**: Inconsistent rate limiting behavior
- **System Health**: Redis infrastructure degraded
- **Availability**: Service continues but without rate limit protection

**Fail-Open Behavior:**
```python
# In redis_limiter.py
except RedisError as e:
    logger.error("rate_limit_redis_error", error=str(e))
    return True  # Allow request (fail open)
```

This prevents outages but removes rate limiting protection.

---

## Diagnosis

### 1. Check Dashboard

Navigate to **Grafana → 10 - Redis Rate Limiting** dashboard:

- **Redis Errors by Type (errors/s)**: Identify error type
- **Lua Script Executions**: Script failures?
- **Redis Connection Pool Status**: Pool exhaustion?
- **Rate Limit Check Latency**: Performance degradation?

### 2. Query Prometheus

```promql
# Error rate by type
sum(rate(redis_rate_limit_errors_total[5m])) by (error_type)

# Lua script failure rate
sum(rate(redis_lua_script_executions_total{status="error"}[5m]))

# Total error rate
sum(rate(redis_rate_limit_errors_total[5m]))
```

### 3. Check Application Logs

```bash
# Recent rate limit errors
kubectl logs -l app=lia-api --tail=100 | jq 'select(.event == "rate_limit_redis_error")'

# Error types and frequencies
kubectl logs -l app=lia-api --tail=500 | jq -r 'select(.event == "rate_limit_redis_error") | .error_type' | sort | uniq -c | sort -rn

# Full error details
kubectl logs -l app=lia-api --tail=50 | jq 'select(.event == "rate_limit_redis_error") | {error_type, error, key, duration_ms}'
```

### 4. Check Redis Server

```bash
# Connect to Redis
kubectl exec -it redis-0 -- redis-cli

# Check for errors in Redis log
kubectl logs redis-0 --tail=100 | grep -i error

# Check Redis health
INFO server
INFO stats

# Check error stats
INFO errorstats
```

---

## Common Error Types

### 1. ConnectionError

**Cause**: Cannot connect to Redis server

**Symptoms:**
```
error_type: "ConnectionError"
error: "Error connecting to Redis"
```

**Diagnosis:**
```bash
# Check if Redis is running
kubectl get pods -l app=redis

# Check Redis service
kubectl get svc redis-service

# Test connection from API pod
kubectl exec -it $(kubectl get pod -l app=lia-api -o jsonpath='{.items[0].metadata.name}') -- redis-cli -h redis-service PING
```

**Resolution:**
- Check Redis pod status
- Verify network connectivity
- Check DNS resolution
- Review service/endpoint configuration

### 2. TimeoutError

**Cause**: Redis operation took too long

**Symptoms:**
```
error_type: "TimeoutError"
error: "Timeout reading from socket"
```

**Diagnosis:**
```promql
# Check Redis latency
1000 * histogram_quantile(0.95, sum(rate(redis_rate_limit_check_duration_seconds_bucket[5m])) by (le))

# Check Redis CPU/memory
kubectl top pod redis-0
```

**Resolution:**
- Increase timeout values
- Scale Redis resources
- Optimize slow operations

### 3. ResponseError

**Cause**: Redis returned an error response

**Symptoms:**
```
error_type: "ResponseError"
error: "NOSCRIPT No matching script. Please use EVAL."
```

**Diagnosis:**
```bash
# Check if Lua script is loaded
kubectl exec -it redis-0 -- redis-cli SCRIPT EXISTS <sha>
```

**Resolution:**
```bash
# Flush scripts (will auto-reload)
kubectl exec -it redis-0 -- redis-cli SCRIPT FLUSH

# Or restart Redis
kubectl rollout restart statefulset/redis
```

### 4. RedisClusterError

**Cause**: Redis cluster issue (if using cluster mode)

**Symptoms:**
```
error_type: "RedisClusterError"
error: "MOVED 1234 127.0.0.1:7001"
```

**Resolution:**
- Check cluster topology
- Fix cluster configuration
- Ensure client supports cluster mode

### 5. OutOfMemoryError

**Cause**: Redis out of memory

**Symptoms:**
```
error_type: "ResponseError"
error: "OOM command not allowed when used memory > 'maxmemory'"
```

**Diagnosis:**
```bash
kubectl exec -it redis-0 -- redis-cli INFO memory
# Look for: used_memory, maxmemory, evicted_keys
```

**Resolution:**
- Increase Redis memory limits
- Enable eviction policy
- Clean up old keys

---

## Resolution Steps

### Immediate Actions (Incident Response)

#### Option 1: Identify and Fix Root Cause

**Based on error type:**

1. **ConnectionError** → Check Redis availability
   ```bash
   kubectl get pods -l app=redis
   kubectl logs redis-0 --tail=50
   ```

2. **TimeoutError** → Scale Redis or increase timeouts
   ```python
   # In redis.py
   redis_client = Redis(
       socket_timeout=10,  # Increase from 5
       socket_connect_timeout=10,
   )
   ```

3. **ResponseError (NOSCRIPT)** → Reload Lua script
   ```bash
   kubectl exec -it redis-0 -- redis-cli SCRIPT FLUSH
   kubectl rollout restart deployment/lia-api
   ```

4. **OutOfMemoryError** → Increase memory or clean up
   ```bash
   # Temporary: increase maxmemory
   kubectl exec -it redis-0 -- redis-cli CONFIG SET maxmemory 4gb

   # Permanent: update config
   kubectl edit configmap redis-config
   ```

#### Option 2: Restart Redis (Last Resort)

**⚠️ WARNING: May cause brief downtime**

```bash
# Graceful restart
kubectl rollout restart statefulset/redis

# Monitor recovery
watch -n 2 'kubectl exec -it redis-0 -- redis-cli PING'
```

#### Option 3: Increase Error Tolerance

**Temporary workaround:**

```python
# In redis_limiter.py
async def acquire(self, key, max_calls, window_seconds):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # ... existing code ...
            return allowed
        except RedisError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff
                continue
            else:
                # After retries, fail open
                logger.error("rate_limit_redis_error_after_retries", error=str(e))
                return True
```

### Short-Term Actions (1-24 hours)

1. **Implement Error Tracking Dashboard**

Add panel to Grafana:
```promql
# Error rate over time
sum(rate(redis_rate_limit_errors_total[5m])) by (error_type)

# Error percentage
100 * sum(rate(redis_rate_limit_errors_total[5m])) / sum(rate(redis_rate_limit_check_duration_seconds_count[5m]))
```

2. **Add Detailed Error Logging**

```python
# In redis_limiter.py
except RedisError as e:
    error_type = type(e).__name__
    redis_rate_limit_errors_total.labels(error_type=error_type).inc()

    logger.error(
        "rate_limit_redis_error",
        error_type=error_type,
        error=str(e),
        key=key,
        key_prefix=key_prefix,
        max_calls=max_calls,
        window_seconds=window_seconds,
        # Additional context
        traceback=traceback.format_exc(),
        redis_info=await self._get_redis_info(),
    )
```

3. **Implement Health Checks**

```python
# In redis.py
class RedisHealthCheck:
    async def check_health(self) -> dict:
        try:
            # Ping test
            await redis_client.ping()

            # Write/read test
            test_key = "health_check_test"
            await redis_client.set(test_key, "ok", ex=10)
            value = await redis_client.get(test_key)

            # Lua script test
            result = await redis_client.eval("return 1", 0)

            return {
                "status": "healthy",
                "ping": True,
                "read_write": value == b"ok",
                "lua_script": result == 1,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

# Expose as endpoint
@app.get("/health/redis")
async def redis_health():
    return await redis_health_check.check_health()
```

### Long-Term Actions (1-7 days)

1. **Implement Circuit Breaker**

```python
from circuitbreaker import circuit

class CircuitBreakerRedisRateLimiter(RedisRateLimiter):
    @circuit(failure_threshold=10, recovery_timeout=30)
    async def acquire(self, key, max_calls, window_seconds):
        return await super().acquire(key, max_calls, window_seconds)

    # When circuit opens (after 10 failures):
    # - Automatically fail open for 30 seconds
    # - Prevents cascading failures
    # - Auto-recovers when Redis healthy
```

2. **Deploy Redis High Availability**

```yaml
# redis-ha.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-ha
spec:
  replicas: 3
  serviceName: redis-ha
  template:
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
      - name: sentinel
        image: redis:7-alpine
        command: ["redis-sentinel", "/etc/redis/sentinel.conf"]
```

Benefits:
- Automatic failover
- Zero downtime for Redis upgrades
- Better error tolerance

3. **Implement Fallback Rate Limiting**

```python
class HybridRateLimiter:
    def __init__(self, redis_limiter, local_limiter):
        self.redis_limiter = redis_limiter
        self.local_limiter = local_limiter  # In-memory fallback

    async def acquire(self, key, max_calls, window_seconds):
        try:
            # Try Redis first (distributed)
            return await self.redis_limiter.acquire(key, max_calls, window_seconds)
        except RedisError:
            # Fallback to local (not distributed, but better than nothing)
            logger.warning("rate_limit_fallback_to_local", key=key)
            return await self.local_limiter.acquire(key, max_calls, window_seconds)
```

---

## Verification

After applying fixes:

```promql
# Error rate should be zero
sum(rate(redis_rate_limit_errors_total[5m])) == 0

# Lua script success rate 100%
100 * sum(rate(redis_lua_script_executions_total{status="success"}[5m])) / sum(rate(redis_lua_script_executions_total[5m])) == 100

# No connection pool issues
100 * (1 - (redis_connection_pool_available_current / redis_connection_pool_size_current)) < 70
```

**Success Criteria:**
- ✅ Zero Redis errors for 30 minutes
- ✅ Lua script success rate 100%
- ✅ Normal rate limiting behavior
- ✅ No application errors related to rate limiting

---

## Prevention

1. **Monitoring & Alerting**:
   - Alert on >1 error/sec (warning)
   - Monitor error types and trends
   - Track error percentage

2. **Redis Health Monitoring**:
   - CPU, memory, network metrics
   - Slow query log
   - Command statistics

3. **Testing**:
   - Chaos testing (kill Redis pod)
   - Load testing with Redis failures
   - Verify fail-open behavior

4. **Infrastructure**:
   - Deploy Redis HA/Sentinel
   - Implement circuit breakers
   - Regular Redis maintenance

---

## Related Alerts

- `RedisDown`: Redis server unavailable
- `RedisRateLimitCheckLatencyHigh`: Performance issues
- `RedisConnectionPoolExhaustion`: Connection pool saturated
- `RedisLuaScriptFailureRateHigh`: Lua script failures

---

## References

- **Code**: `apps/api/src/infrastructure/rate_limiting/redis_limiter.py` (lines 242-267)
- **Metrics**: `apps/api/src/infrastructure/observability/metrics_redis.py`
- **Redis Config**: `infrastructure/redis/redis.conf`
- **Dashboard**: Grafana → 10 - Redis Rate Limiting
- **Alerts**: `infrastructure/observability/prometheus/alerts.yml` (line 361)

---

## Escalation

**L1 Support**: Check dashboard, identify error type
**L2 Support**: Analyze logs, check Redis health
**L3 Support**: Fix configuration, restart services
**Engineering**: Implement circuit breaker, deploy HA

**On-Call Contact**: `@platform-team` in Slack #incidents channel

---

**Last Updated**: 2025-11-22
**Version**: 1.0
**Owner**: Platform Team
