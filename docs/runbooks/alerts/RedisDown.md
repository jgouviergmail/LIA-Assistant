# RedisDown - Runbook

**Severity**: critical
**Component**: redis
**Impact**: Cache, rate limiting, background chat run streams (ADR-117) and SSE resume are all down. The API degrades hard or errors.
**SLA Impact**: Yes — chat availability and latency.

---

## 1. Alert Definition

**Alert Name**: `RedisDown`

**Prometheus Expression**:
```promql
up{job="redis"} == 0 or redis_up == 0
```

`up{job="redis"} == 0` fires when redis-exporter itself is unreachable; `redis_up == 0` fires when the exporter runs but cannot reach Redis. Both mean the same operational emergency.

**Firing Duration**: `for: 2m`

**Labels**: `severity: critical`, `component: redis`, `tier: core`

---

## 2. Symptoms

### What Users See
- Chat requests fail or hang; background runs cannot be resumed.
- Login/session flows may fail (rate limiter errors).

### What Ops See
- `redis_up == 0` in Prometheus, Redis panels empty in Grafana dashboard 03.
- API logs: connection errors from `redis.asyncio` (structlog events with `redis` in the logger name).

---

## 3. Possible Causes

### Cause 1: Container stopped / crashed (High Likelihood)
```bash
docker ps -a --filter name=redis
docker logs --tail 100 lia-redis-prod
```
Look for OOM kill (`exit code 137`) — the prod memory limit is deliberately tight (128M).

### Cause 2: AOF corruption after power loss (Medium Likelihood, RPi5)
```bash
docker logs lia-redis-prod 2>&1 | grep -i "aof\|corrupt"
```

### Cause 3: Password mismatch after .env change (Low Likelihood)
Exporter and API both read `REDIS_PASSWORD`; a rotation applied to only one side looks like "Redis down".

---

## 4. Resolution Steps

### Immediate Mitigation
```bash
docker restart lia-redis-prod
# Verify:
docker exec lia-redis-prod redis-cli -a "$REDIS_PASSWORD" ping   # → PONG
```

### If AOF is corrupted
```bash
docker exec lia-redis-prod redis-check-aof --fix /data/appendonly.aof
docker restart lia-redis-prod
```
Redis content is cache/ephemeral state — a flush loses stream resume buffers and rate-limit windows, not durable data (PostgreSQL holds all persistence).

### Post-Recovery Verification
- `redis_up == 1` in Prometheus; alert resolves (email `[RESOLVED]` arrives).
- Send a chat message end-to-end in the app.
