# Runbook: RedisRateLimitHighHitRate

**Alert Name**: `RedisRateLimitHighHitRate`
**Severity**: Critical
**Component**: Redis Rate Limiting
**Type**: Rate Limiting

---

## Description

Rate limit hit rate is excessively high (>50%), meaning more than half of all requests are being rejected by the rate limiter. This indicates users are severely impacted and cannot perform their actions.

**Threshold**:
- **Critical**: >50% hit rate for 10 minutes
- **Warning**: >30% hit rate for 15 minutes (`RedisRateLimitModerateHitRate`)

---

## Impact

- **User Experience**: Majority of user requests fail with 429 Too Many Requests
- **Business Impact**: Users cannot complete tasks, potential revenue loss
- **System Health**: Rate limiter working as designed, but limits may be too restrictive

---

## Diagnosis

### 1. Check Dashboard

Navigate to **Grafana → 10 - Redis Rate Limiting** dashboard:

- **Rate Limit Hit Rate (%)**: Verify current hit rate
- **Hit Rate by Endpoint (%)**: Identify which endpoints are affected
- **Top Endpoints by Rate Limit Hits**: See which endpoints have highest rejection rate

### 2. Query Prometheus

```promql
# Current hit rate by endpoint
100 * sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix)
/ (sum(rate(redis_rate_limit_allows_total[5m])) by (key_prefix) + sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix))

# Total requests per second by endpoint
sum(rate(redis_rate_limit_allows_total[5m])) by (key_prefix) + sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix)

# Rejected requests per second
sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix)
```

### 3. Check Application Logs

```bash
# Check for rate limit errors in API logs
kubectl logs -l app=lia-api --tail=100 | grep -i "rate.*limit"

# Check structlog events
kubectl logs -l app=lia-api --tail=500 | jq 'select(.event == "rate_limit_check" and .allowed == false)'
```

### 4. Identify Root Cause

**Possible causes:**

1. **Legitimate traffic spike**: Sudden increase in user activity
2. **Bot/abuse**: Automated script hitting endpoints repeatedly
3. **Inefficient client**: Frontend making too many API calls
4. **Misconfigured limits**: Rate limits too low for normal usage
5. **Single user abuse**: One user/IP making excessive requests

---

## Resolution Steps

### Immediate Actions (Incident Response)

#### Option 1: Increase Rate Limits (Temporary Relief)

**⚠️ WARNING**: Only if traffic is legitimate and urgent.

```python
# In apps/api/src/core/config/security.py
# Increase limits temporarily (requires deployment)

RATE_LIMIT_PER_MINUTE = 100  # Was: 60
RATE_LIMIT_BURST = 20        # Was: 10
```

```bash
# Redeploy API
kubectl rollout restart deployment/lia-api

# Monitor impact
watch -n 5 'kubectl exec -it redis-0 -- redis-cli info | grep connected_clients'
```

#### Option 2: Reset Rate Limit for Specific Key (Emergency)

**⚠️ USE WITH CAUTION**: Only for false positives.

```python
# Connect to Redis
kubectl exec -it redis-0 -- redis-cli

# List rate limit keys
KEYS user:*:*

# Check specific key window
ZCARD user:123:contacts_search
ZRANGE user:123:contacts_search 0 -1 WITHSCORES

# Delete key (resets rate limit)
DEL user:123:contacts_search
```

#### Option 3: Block Abusive User/IP (Attack Response)

```bash
# Identify top offenders
kubectl logs -l app=lia-api --tail=1000 | jq -r 'select(.event == "rate_limit_check" and .allowed == false) | .user_id' | sort | uniq -c | sort -rn | head -10

# Temporary IP block (if applicable)
# Add to nginx/ingress deny list
kubectl edit configmap nginx-config
# Add: deny <IP>;

# Permanent user suspension (database)
kubectl exec -it postgres-0 -- psql lia -c "UPDATE users SET is_active = false WHERE id = '<user_id>';"
```

### Short-Term Actions (1-24 hours)

1. **Analyze Traffic Patterns**

```bash
# Export metrics to CSV for analysis
curl 'http://prometheus:9090/api/v1/query_range?query=sum(rate(redis_rate_limit_hits_total[5m]))%20by%20(key_prefix)&start=<start>&end=<end>&step=60' > rate_limit_hits.json

# Analyze in Python/Excel:
# - Time of day patterns
# - User distribution
# - Endpoint distribution
```

2. **Review Client Code**

Check if frontend/mobile clients are:
- Polling too frequently
- Retrying failed requests without backoff
- Making redundant API calls
- Not caching responses

3. **Implement Client-Side Optimizations**

```typescript
// Example: Add exponential backoff
const retryWithBackoff = async (fn, maxRetries = 3) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (error.status === 429) {
        const delay = Math.pow(2, i) * 1000; // Exponential backoff
        await sleep(delay);
      } else {
        throw error;
      }
    }
  }
  throw new Error('Max retries exceeded');
};
```

### Long-Term Actions (1-7 days)

1. **Implement Adaptive Rate Limiting**

```python
# Different limits per user tier
def get_rate_limit(user: User) -> tuple[int, int]:
    if user.tier == "premium":
        return (200, 40)  # Higher limits
    elif user.tier == "free":
        return (60, 10)   # Standard limits
    else:
        return (30, 5)    # Lower limits for trial
```

2. **Add Rate Limit Headers**

```python
# In FastAPI middleware
response.headers["X-RateLimit-Limit"] = str(max_calls)
response.headers["X-RateLimit-Remaining"] = str(max_calls - current_usage)
response.headers["X-RateLimit-Reset"] = str(int(time.time() + window_seconds))
```

Clients can then:
- Display rate limit status in UI
- Proactively throttle requests
- Show countdown timer before retry

3. **Create Rate Limit Budget Dashboard**

Add panel to Grafana showing:
- Current usage vs. limits per endpoint
- Estimated time until limit reset
- Historical usage trends

4. **Implement Circuit Breaker Pattern**

```python
# Backend service protection
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def call_google_api(...):
    # If 5 failures, stop calling for 60s
    ...
```

---

## Verification

After applying fixes, verify resolution:

```promql
# Hit rate should drop below 30%
100 * sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix)
/ (sum(rate(redis_rate_limit_allows_total[5m])) by (key_prefix) + sum(rate(redis_rate_limit_hits_total[5m])) by (key_prefix))

# Check latency is normal (<10ms P95)
1000 * histogram_quantile(0.95, sum(rate(redis_rate_limit_check_duration_seconds_bucket[5m])) by (le))

# Verify no errors
sum(rate(redis_rate_limit_errors_total[5m])) by (error_type)
```

**Success Criteria:**
- ✅ Hit rate < 10% sustained for 30 minutes
- ✅ No user complaints about 429 errors
- ✅ Normal traffic volume
- ✅ No Redis errors

---

## Prevention

1. **Set up proactive monitoring alerts**:
   - Hit rate > 10% for 30 minutes (warning)
   - Sudden traffic spike detection

2. **Regular capacity planning**:
   - Review rate limit usage weekly
   - Adjust limits based on user growth

3. **Load testing**:
   - Test rate limiting under load
   - Verify limits match SLAs

4. **Documentation**:
   - Document rate limits in API docs
   - Provide guidelines to API consumers

---

## Related Alerts

- `RedisRateLimitModerateHitRate`: Warning-level hit rate (>30%)
- `RedisRateLimitCheckLatencyHigh`: Rate limiting slow to respond
- `RedisConnectionPoolExhaustion`: Redis pool saturated
- `RedisRateLimitErrorsHigh`: Redis errors during rate limiting

---

## References

- **Code**: `apps/api/src/infrastructure/rate_limiting/redis_limiter.py`
- **Config**: `apps/api/src/core/config/security.py`
- **Metrics**: `apps/api/src/infrastructure/observability/metrics_redis.py`
- **Dashboard**: Grafana → 10 - Redis Rate Limiting
- **Alerts**: `infrastructure/observability/prometheus/alerts.yml` (line 268)

---

## Escalation

**L1 Support**: Check dashboard, gather metrics
**L2 Support**: Analyze logs, identify root cause
**L3 Support**: Adjust configuration, deploy fixes
**Engineering**: Implement long-term optimizations

**On-Call Contact**: `@backend-team` in Slack #incidents channel

---

**Last Updated**: 2025-11-22
**Version**: 1.0
**Owner**: Backend Team
