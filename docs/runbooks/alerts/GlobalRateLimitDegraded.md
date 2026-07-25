# GlobalRateLimitDegraded - Runbook

**Severity**: warning
**Component**: api
**Impact**: The API is serving requests with **no global rate limit applied**. Nothing is broken for users; the abuse ceiling is simply absent until Redis is reachable again.
**SLA Impact**: No — this is a security-posture alert, not an availability one.

---

## 1. Alert Definition

**Alert Name**: `GlobalRateLimitDegraded`

**Prometheus Expression**:
```promql
sum(rate(http_rate_limit_degraded_total[5m])) > 0.01
```

**Firing Duration**: `for: 5m`

**Labels**: `severity: warning`, `component: api`, `tier: core`

**Threshold**: `ALERT_CORE_RATE_LIMIT_DEGRADED_RPS` in `infrastructure/observability/prometheus/thresholds/{env}.env`. It is deliberately not `> 0`: an isolated Redis timeout admits one request unchecked, which is not an incident. 0.01 req/s sustained over five minutes is roughly three unprotected requests — a degradation.

---

## 2. Why this alert exists

`RateLimitMiddleware` (SEC-016) **fails open**: when it cannot reach Redis, the request is admitted rather than refused. On a single-instance deployment the alternative is worse — failing closed would turn a cache outage into a total outage, a self-inflicted denial of service.

That trade-off is only defensible while the unprotected window is *visible*. Every increment of `http_rate_limit_degraded_total` is one request that crossed the API with no ceiling applied. This alert is the honesty mechanism attached to the policy; without it, the API could run unprotected indefinitely and nothing would say so.

**Distinct from `RedisDown`**: that alert fires when redis-exporter reports Redis gone. This one fires when the API *cannot use* Redis — which also covers a saturated connection pool, a network partition, or an authentication failure while Redis is perfectly up. Seeing this alert without `RedisDown` is informative in itself.

---

## 3. Symptoms

### What Users See
Nothing. Requests succeed normally — that is precisely the risk.

### What Ops See
- `http_rate_limit_degraded_total` climbing (Grafana dashboard 04 — HTTP/API).
- API logs carry `global_rate_limit_check_failed` with the failing path and the exception text:
  ```bash
  docker logs --tail 200 lia-api-prod 2>&1 | grep global_rate_limit_check_failed
  ```
- Frequently accompanied by `redis_rate_limit_errors_total` rising (the shared limiter behind this middleware).

---

## 4. Possible Causes

### Cause 1: Redis is down or restarting (High Likelihood)
```bash
docker ps -a --filter name=lia-redis-prod
docker exec lia-redis-prod redis-cli -a "$REDIS_PASSWORD" ping   # → PONG
```
If Redis is genuinely down, `RedisDown` is firing too — treat that runbook as the primary and this alert as its security consequence.

### Cause 2: Connection pool exhausted, Redis healthy (Medium Likelihood)
Redis answers `PING` but the API cannot obtain a connection. See `RedisConnectionPoolExhaustion.md`.
```bash
docker exec lia-redis-prod redis-cli -a "$REDIS_PASSWORD" info clients
```

### Cause 3: Password rotated on one side only (Low Likelihood)
`REDIS_PASSWORD` changed in `.env` but the API container was not recreated. Redis is up, the exporter is green, and only the API fails — this alert fires alone.
```bash
docker exec lia-api-prod env | grep -c REDIS_PASSWORD   # present?
docker logs --tail 50 lia-api-prod 2>&1 | grep -i "auth\|NOAUTH"
```

---

## 5. Resolution Steps

### Immediate Mitigation
Restore Redis reachability — the limiter recovers on its own, no API restart required:
```bash
docker restart lia-redis-prod
docker exec lia-redis-prod redis-cli -a "$REDIS_PASSWORD" ping
```

For cause 3, recreate the API so it picks up the current secret:
```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate api
```

### If the degradation persists under load
The limit is absent, so an abusive client is unbounded meanwhile. Check whether the traffic is hostile before deciding to wait:
```promql
topk(5, sum by (country) (rate(http_requests_by_country_total[5m])))
```
Cloudflare rate limiting at the edge is the mitigation of last resort while Redis is repaired.

### Post-Recovery Verification
- `rate(http_rate_limit_degraded_total[5m])` returns to 0; the alert resolves (`[RESOLVED]` email arrives).
- A burst above `RATE_LIMIT_GLOBAL_PER_MINUTE` now answers 429 with a `Retry-After` header.

---

## 6. Related

- `RedisDown.md` — the usual root cause.
- `RedisConnectionPoolExhaustion.md` — Redis up, connections unavailable.
- `docs/technical/RATE_LIMITING.md` — the full limiter design and the fail-open rationale.
