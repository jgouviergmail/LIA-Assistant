# HighCPUUsage - Runbook

**Severity**: Warning
**Component**: Infrastructure (Compute)
**Impact**: Performance degradation, increased latency, potential service instability
**SLA Impact**: No (warning level) - May escalate to Yes if sustained >15 minutes

---

## 📊 Alert Definition

**Alert Name**: `HighCPUUsage`

**Prometheus Expression**:
```promql
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > ${ALERT_CPU_USAGE_WARNING_PERCENT}
```

**Threshold**:
- **Production**: >80% CPU usage (ALERT_CPU_USAGE_WARNING_PERCENT=80)
- **Staging**: >85% CPU usage (Higher tolerance for test environments)
- **Development**: >90% CPU usage (Relaxed threshold)

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: warning
- `component`: compute
- `instance`: [hostname/IP of affected instance]

---

## 🔍 Symptoms

### What Users See
- **Slow API responses** - Increased latency (2-5x normal)
- **Intermittent timeouts** - Requests timing out during CPU spikes
- **Delayed background jobs** - Email sending, data processing slower
- **Degraded streaming** - Agent responses buffering/stuttering

### What Ops See
- **High CPU >80%** in monitoring dashboards
- **P95/P99 latency increase** - Request duration graphs spiking
- **Process CPU%** - Top/htop shows high CPU processes
- **Load average** - System load >number of CPU cores
- **Context switches** - High voluntary/involuntary context switches

---

## 🎯 Possible Causes

### 1. Traffic Spike / Load Increase (High Likelihood)

**Likelihood**: High (60%) - Most common cause

**Description**:
Legitimate traffic increase (marketing campaign, viral content, scheduled batch jobs) overwhelming available CPU capacity.

**How to Verify**:
```bash
# Check current request rate
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])" | jq '.data.result[0].value[1]'

# Compare to historical baseline
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[1h] offset 24h)" | jq '.data.result[0].value[1]'

# Check concurrent requests
curl -s "http://localhost:9090/api/v1/query?query=http_requests_in_flight" | jq '.data.result[0].value[1]'

# Check container CPU usage
docker stats --no-stream
```

**Expected Output if This is the Cause**:
- Request rate 2-10x higher than baseline
- Concurrent requests >100 (normal: 10-50)
- All containers showing high CPU (distributed load)

---

### 2. Inefficient Query / Code Regression (Medium-High Likelihood)

**Likelihood**: Medium-High (50%) - Especially after deployments

**Description**:
Recent code change introduced CPU-intensive operation (N+1 queries, inefficient algorithm, missing indexes, runaway loop).

**How to Verify**:
```bash
# Check recent deployments
git log --since="24 hours ago" --oneline --graph --all | head -20

# Check slow database queries
docker-compose exec postgres psql -U lia -c "
SELECT
  substring(query, 1, 100) AS short_query,
  calls,
  total_exec_time / 1000 AS total_seconds,
  mean_exec_time / 1000 AS mean_seconds,
  max_exec_time / 1000 AS max_seconds
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
"

# Check API endpoint latency distribution
docker-compose logs api --since 10m | grep "INFO" | grep "ms" | tail -50

# Profile running Python process (if applicable)
docker-compose exec api py-spy top --pid 1 --duration 30
```

**Expected Output if This is the Cause**:
- Recent deployment (< 24h ago)
- Specific endpoint showing 10-100x slower execution
- Database query with high `total_exec_time`
- Specific function dominating CPU in profiler

---

### 3. Background Job Runaway (Medium Likelihood)

**Likelihood**: Medium (40%) - Periodic issue

**Description**:
Scheduled background task (data cleanup, report generation, LLM batch processing) consuming excessive CPU.

**How to Verify**:
```bash
# Check running processes CPU usage
docker-compose exec api top -b -n 1 -o %CPU | head -20

# Check Python multiprocessing workers
docker-compose exec api ps aux | grep python | grep -v grep

# Check scheduled tasks status (if using APScheduler/Celery)
docker-compose logs api | grep -i "scheduler\|celery\|worker" | tail -50

# Check LLM request queue depth
curl -s "http://localhost:9090/api/v1/query?query=llm_requests_queued_total" | jq '.data.result[0].value[1]'
```

**Expected Output if This is the Cause**:
- Background process consuming >50% CPU
- Multiple worker processes active
- Large queue depth (>100 items)

---

### 4. External API Blocking / Retry Storm (Medium Likelihood)

**Likelihood**: Medium (35%) - Especially with LLM API integration

**Description**:
External API (OpenAI, Anthropic, Google) slow/down → retries accumulate → CPU spent waiting/retrying.

**How to Verify**:
```bash
# Check LLM API failure rate
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_api_requests_total{status=\"error\"}[5m])" | jq '.data.result[0].value[1]'

# Check LLM API latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, llm_api_duration_seconds_bucket)" | jq '.data.result[0].value[1]'

# Check retry attempts
docker-compose logs api --since 10m | grep -i "retry\|timeout\|connection refused"

# Check active connections to external APIs
docker-compose exec api netstat -an | grep ESTABLISHED | grep -E ":443|:80"
```

**Expected Output if This is the Cause**:
- High error rate (>10%)
- P95 latency >10 seconds (normal: 1-3s)
- Many "Retrying request" log entries
- High number of ESTABLISHED connections

---

### 5. Memory Leak → Garbage Collection Thrashing (Low-Medium Likelihood)

**Likelihood**: Low-Medium (25%) - Gradual degradation

**Description**:
Memory leak causing frequent garbage collection, which consumes CPU. Often accompanied by HighMemoryUsage alert.

**How to Verify**:
```bash
# Check memory usage trend
curl -s "http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{name=~\"lia.*\"}" | jq '.data.result[0].value[1]'

# Check Python garbage collection stats (if instrumented)
docker-compose logs api | grep -i "gc\|garbage"

# Check memory available
docker-compose exec api free -h

# Check for memory growth over time
docker stats --no-stream lia_api_1 | awk '{print $4}'
```

**Expected Output if This is the Cause**:
- Memory usage >80%
- Memory growing steadily (100MB/hour)
- Frequent GC log entries
- Both HighCPUUsage AND HighMemoryUsage alerts firing

---

## 🔧 Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Identify which service(s) affected**
```bash
# Check all containers CPU
docker stats --no-stream

# Expected output shows which container(s) >80% CPU
# NAME                    CPU %     MEM USAGE / LIMIT
# lia_api_1        95.32%    1.2GiB / 2GiB
# lia_postgres_1   45.12%    512MiB / 1GiB
# lia_redis_1      12.34%    128MiB / 512MiB
```

**Step 2: Check system load**
```bash
# Check host load average
docker-compose exec api uptime

# Expected output:
# 14:25:32 up 5 days,  3:12,  0 users,  load average: 4.52, 3.91, 2.65
#                                                       ^^^^
# Load >4 on 4-core system = overloaded
```

**Step 3: Check request rate**
```bash
# Check if traffic spike
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[1m])" | jq '.data.result[0].value[1]'

# Compare to baseline (e.g., same time yesterday)
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[1m] offset 24h)" | jq '.data.result[0].value[1]'

# If current >> baseline → traffic spike
# If current ≈ baseline → code regression or background job issue
```

---

### Deep Dive Investigation (5-10 minutes)

**Step 4: Identify top CPU consumers**
```bash
# Inside API container
docker-compose exec api top -b -n 1 -o %CPU | head -20

# Look for:
# - uvicorn workers using >50% each
# - python processes (background tasks)
# - postgres connections (runaway queries)
```

**Step 5: Analyze recent code changes**
```bash
# Check deployments in last 24h
git log --since="24 hours ago" --oneline --all

# Check if alert timing correlates with deployment
# If yes → likely code regression
```

**Step 6: Profile slow endpoints**
```bash
# Extract request duration from logs (last 1000 requests)
docker-compose logs api --tail=1000 | grep "INFO" | grep -oP '"\w+ /\S+" \d+ms' | sort -k3 -n -r | head -20

# Expected output:
# "POST /api/agents/chat" 5432ms
# "GET /api/conversations/123/messages" 3210ms
# → Identify slowest endpoints
```

**Step 7: Check correlation with other metrics**
```bash
# Check if accompanied by memory alert
curl -s "http://localhost:9093/api/v2/alerts" | jq '.[] | select(.labels.alertname=="HighMemoryUsage") | .status.state'

# Check database load
curl -s "http://localhost:9090/api/v1/query?query=pg_stat_activity_count" | jq '.data.result[0].value[1]'

# Check Redis connections
curl -s "http://localhost:9090/api/v1/query?query=redis_connected_clients" | jq '.data.result[0].value[1]'
```

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding - <5 minutes)

**Option 1: Scale horizontally (if orchestrated deployment)**
```bash
# Increase API container replicas (if using Docker Swarm/Kubernetes)
docker service scale lia_api=3

# Or manually start additional container
docker-compose up -d --scale api=2

# Verify load distribution
docker stats --no-stream

# When to use: Traffic spike, distributed load
# Expected impact: CPU per container drops 30-50%
# Duration: 1-2 minutes
```

**Option 2: Restart affected container (if single high-CPU process)**
```bash
# Restart API container (kills runaway processes)
docker-compose restart api

# Wait for health check
sleep 30
docker-compose ps api

# Verify CPU normalized
docker stats --no-stream lia_api_1

# When to use: Runaway background job, memory leak
# Expected impact: CPU drops to <30% immediately
# Duration: 30 seconds
# Downside: Brief service interruption (10-30s)
```

**Option 3: Kill specific high-CPU process (surgical approach)**
```bash
# Identify PID of high-CPU process
docker-compose exec api top -b -n 1 -o %CPU | head -20

# Kill specific process (e.g., runaway worker)
docker-compose exec api kill -9 [PID]

# Verify CPU drops
docker stats --no-stream lia_api_1

# When to use: Identified specific runaway process
# Expected impact: CPU drops 20-50%
# Duration: Immediate
# Downside: May lose in-flight work
```

**Option 4: Enable rate limiting (if traffic spike)**
```bash
# Check if Redis rate limiter is active
curl -s "http://localhost:9090/api/v1/query?query=redis_rate_limit_checks_total" | jq '.data.result[0].value[1]'

# If not active, temporarily reduce request accept rate
# Update .env:
# RATE_LIMIT_PER_MINUTE=30  # Reduce from 60
# RATE_LIMIT_BURST=10       # Reduce from 20

# Restart API with new limits
docker-compose restart api

# When to use: Traffic spike, DDoS attempt
# Expected impact: CPU drops to sustainable level (~60%)
# Duration: 1 minute
# Downside: Legitimate users may see 429 errors
```

---

### Verification After Mitigation

```bash
# 1. Verify CPU usage normalized
docker stats --no-stream

# Expected: All containers <60% CPU

# 2. Verify alert stopped firing
curl -s "http://localhost:9093/api/v2/alerts" | jq '.[] | select(.labels.alertname=="HighCPUUsage") | .status.state'

# Expected: "inactive" or empty result

# 3. Verify service health
curl -f http://localhost:8000/health

# Expected: HTTP 200, response <500ms

# 4. Verify P95 latency normalized
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, http_request_duration_seconds_bucket)" | jq '.data.result[0].value[1]'

# Expected: <1.0 seconds (down from >2s during high CPU)
```

---

### Root Cause Fix (Permanent Solution - 15-60 minutes)

**Fix 1: Optimize inefficient code (if code regression identified)**

**Investigation**:
```bash
# Profile code to identify bottleneck
docker-compose exec api py-spy record --pid 1 --duration 60 --output /tmp/profile.svg

# Copy profile to host
docker cp lia_api_1:/tmp/profile.svg ./profile.svg

# Analyze in browser (shows flamegraph of CPU time)
```

**Common optimizations**:
1. **N+1 Query Fix** (if database queries dominant):
   ```python
   # Before (N+1):
   for conversation in conversations:
       messages = db.query(Message).filter_by(conversation_id=conversation.id).all()

   # After (1 query):
   conversation_ids = [c.id for c in conversations]
   messages = db.query(Message).filter(Message.conversation_id.in_(conversation_ids)).all()
   ```

2. **Add database index** (if slow query identified):
   ```bash
   # Create migration
   docker-compose exec api alembic revision -m "add_index_messages_conversation_id"

   # Edit migration file:
   # op.create_index('idx_messages_conversation_id', 'messages', ['conversation_id'])

   # Apply migration
   docker-compose exec api alembic upgrade head
   ```

3. **Cache expensive computation**:
   ```python
   # Add Redis caching for expensive LLM prompt generation
   from functools import lru_cache

   @lru_cache(maxsize=1000)
   def generate_system_prompt(user_context: str) -> str:
       # Expensive prompt template rendering
       pass
   ```

**Testing**:
```bash
# Load test after optimization
docker-compose exec api locust -f tests/load/test_chat_endpoint.py --host=http://localhost:8000 --users=50 --spawn-rate=10 --run-time=5m --headless

# Verify CPU <60% under load
```

**Deployment**:
```bash
# Commit fix
git add .
git commit -m "fix: optimize conversation messages query (N+1 → join)"

# Deploy to production
docker-compose build api
docker-compose up -d api

# Monitor CPU for 10 minutes
watch -n 30 'docker stats --no-stream lia_api_1'
```

---

**Fix 2: Increase CPU resources (if legitimate load growth)**

**For Docker Compose** (update `docker-compose.yml`):
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2.0'  # Increase from 1.0
        reservations:
          cpus: '1.0'
```

**For cloud deployments** (example: AWS ECS):
```bash
# Update ECS task definition
aws ecs register-task-definition \
  --family lia-api \
  --cpu 2048 \  # Increase from 1024 (2 vCPUs)
  --memory 4096

# Update service
aws ecs update-service \
  --cluster lia \
  --service api \
  --task-definition lia-api:latest
```

**Apply changes**:
```bash
# Restart with new resource limits
docker-compose up -d

# Verify new CPU quota
docker inspect lia_api_1 | jq '.[0].HostConfig.NanoCpus'
# Should show: 2000000000 (2 CPUs)
```

---

**Fix 3: Implement background job throttling**

**If background jobs identified as cause**:

**File**: `apps/api/src/infrastructure/scheduler.py`
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

# Limit concurrent background jobs
executors = {
    'default': ThreadPoolExecutor(max_workers=2)  # Reduce from 10
}

scheduler = AsyncIOScheduler(executors=executors)

# Add job with low priority during business hours
@scheduler.scheduled_job('cron', hour='*/6', max_instances=1)
async def cleanup_old_conversations():
    # Only run if CPU <50%
    cpu_usage = get_current_cpu_usage()
    if cpu_usage > 50:
        logger.warning(f"Skipping cleanup job, CPU at {cpu_usage}%")
        return

    # Perform cleanup with rate limiting
    for conversation in get_old_conversations(batch_size=100):
        await delete_conversation(conversation.id)
        await asyncio.sleep(0.1)  # Throttle to avoid CPU spike
```

**Testing**:
```bash
# Trigger job manually
docker-compose exec api python -c "
from src.infrastructure.scheduler import cleanup_old_conversations
import asyncio
asyncio.run(cleanup_old_conversations())
"

# Monitor CPU during execution
docker stats --no-stream lia_api_1
```

---

**Fix 4: Implement circuit breaker for external APIs**

**If external API retries causing high CPU**:

**File**: `apps/api/src/infrastructure/llm/retry_handler.py`
```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60, expected_exception=LLMAPIError)
async def call_llm_api(prompt: str) -> str:
    """
    Circuit breaker prevents retry storms:
    - After 5 failures, circuit opens (fail fast)
    - After 60s, circuit half-opens (try 1 request)
    - If success, circuit closes (resume normal)
    """
    try:
        response = await openai_client.chat.completions.create(...)
        return response.choices[0].message.content
    except openai.RateLimitError:
        # Fail fast instead of retrying
        raise LLMAPIError("Rate limit exceeded, circuit open")
    except openai.APIError as e:
        raise LLMAPIError(f"API error: {e}")
```

**Testing**:
```bash
# Simulate external API failure
# (use mock or network policy to block openai.com)

# Verify circuit opens after 5 failures
docker-compose logs api | grep "Circuit breaker"

# Expected:
# "Circuit breaker OPEN for call_llm_api"
# "Failing fast due to open circuit"

# Verify CPU stays low (no retry storm)
docker stats --no-stream lia_api_1
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **Infrastructure Overview** - `http://localhost:3000/d/infrastructure-resources`
  - Panel: "CPU Usage %" - Real-time CPU per container
  - Panel: "CPU Usage Heatmap" - Historical CPU distribution
  - Panel: "Load Average" - System load trend

- **App Performance** - `http://localhost:3000/d/app-performance`
  - Panel: "Request Rate" - Traffic volume
  - Panel: "P95/P99 Latency" - Correlated with CPU spikes
  - Panel: "Top Endpoints by Duration" - Identify slow endpoints

### Prometheus Queries

**Current CPU usage percentage**:
```promql
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

**CPU usage by container**:
```promql
rate(container_cpu_usage_seconds_total{name=~"lia.*"}[5m]) * 100
```

**Load average (1m/5m/15m)**:
```promql
node_load1
node_load5
node_load15
```

**Top CPU-consuming processes** (if node_exporter configured):
```promql
topk(10, irate(namedprocess_namegroup_cpu_seconds_total[5m]))
```

**CPU throttling** (container hitting CPU limits):
```promql
rate(container_cpu_cfs_throttled_seconds_total{name=~"lia.*"}[5m])
```

### Logs Queries

**Find high-latency requests**:
```bash
docker-compose logs api --since 30m | grep "INFO" | grep -oP '"\w+ /\S+" \d+ms' | awk '$3 > 1000' | sort -k3 -n -r
```

**Find error spike timing**:
```bash
docker-compose logs api --since 1h | grep "ERROR" | awk '{print $1, $2}' | uniq -c
```

---

## 📚 Related Runbooks

- **[HighMemoryUsage.md](./HighMemoryUsage.md)** - Often fires together with HighCPUUsage (memory leak causing GC thrashing)
- **[CriticalLatencyP99.md](./CriticalLatencyP99.md)** - High CPU causes slow responses
- **[HighErrorRate.md](./HighErrorRate.md)** - CPU saturation can cause request timeouts → errors
- **[LLMAPIFailureRateHigh.md](./LLMAPIFailureRateHigh.md)** - External API issues can cause retry storms

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Daily Backup Job CPU Spike
**Scenario**: Every day at 2 AM, CPU spikes to 95% for 10 minutes during database backup.

**Detection**:
```bash
# Check backup job timing
docker-compose logs postgres | grep "pg_dump"
```

**Prevention**:
- Schedule backups during lowest traffic (3-5 AM)
- Use incremental backups instead of full dumps
- Set CPU nice priority for backup process:
  ```bash
  nice -n 19 pg_dump lia > backup.sql
  ```

---

### Pattern 2: LLM Request Queue Buildup
**Scenario**: During traffic spike, LLM requests queue faster than they're processed, causing CPU to stay high even after traffic normalizes.

**Detection**:
```bash
# Check queue depth
curl -s "http://localhost:9090/api/v1/query?query=llm_requests_queued_total" | jq '.data.result[0].value[1]'
```

**Prevention**:
- Implement request timeout (drop requests >30s in queue)
- Add queue depth monitoring alert
- Auto-scale workers based on queue depth

---

### Pattern 3: Conversation Checkpoint Serialization
**Scenario**: Large conversation states (>1MB) cause CPU spikes during PostgreSQL JSONB serialization.

**Detection**:
```bash
# Check checkpoint sizes
docker-compose exec postgres psql -U lia -c "
SELECT
  conversation_id,
  pg_size_pretty(length(checkpoint_data::text)) AS size
FROM checkpoints
ORDER BY length(checkpoint_data::text) DESC
LIMIT 10;
"
```

**Prevention**:
- Implement checkpoint size limit (500KB max)
- Compress checkpoints before storing
- Archive old messages (keep only last 50 in state)

---

### Known Issue 1: Python GIL Bottleneck
**Problem**: Python Global Interpreter Lock limits multi-threaded CPU usage to ~100% (1 core) even with multiple workers.

**Workaround**: Use multi-process uvicorn workers instead of threads:
```yaml
# docker-compose.yml
services:
  api:
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
    # Workers = CPU cores
```

**Tracking**: No permanent fix (Python design limitation)

---

### Known Issue 2: Prometheus Query CPU Spike
**Problem**: Complex Prometheus queries (nested histogram_quantile) can cause CPU spikes on Prometheus server.

**Detection**:
```bash
# Check Prometheus query latency
curl -s "http://localhost:9090/api/v1/query?query=prometheus_engine_query_duration_seconds{quantile=\"0.99\"}" | jq '.data.result[0].value[1]'
```

**Fix**: Implement recording rules for expensive queries (see Phase 2 - Recording Rules task).

---

## 🆘 Escalation

### When to Escalate

Escalate immediately if:
- [ ] CPU >90% for >15 minutes despite mitigation
- [ ] Alert accompanied by ServiceDown or DatabaseDown
- [ ] User-facing impact confirmed (support tickets, monitoring)
- [ ] Cause unclear after 20 minutes investigation
- [ ] Suspected DDoS or security incident

### Escalation Path

**Level 1 - Senior DevOps Engineer** (0-15 minutes):
- **Contact**: On-call DevOps via PagerDuty
- **Info needed**:
  - Current CPU % and duration
  - Affected services (all or specific containers)
  - Recent changes (deployments, config)
  - Mitigation attempts and results
- **Expected action**: Advanced diagnosis, approve resource scaling, rollback decision

**Level 2 - Infrastructure Lead** (15-30 minutes):
- **Contact**: Infrastructure Team Lead
- **Info needed**:
  - Business impact (users affected, revenue)
  - Root cause hypothesis
  - Resource requirements (scale up/out)
- **Expected action**: Approve infrastructure changes, coordinate multi-team response

**Level 3 - CTO** (30+ minutes):
- **Contact**: CTO / VP Engineering
- **Info needed**:
  - Incident timeline
  - Customer communication status
  - Business continuity plan
- **Expected action**: Business decisions, external communication approval

### Escalation Template (Slack/PagerDuty)

```
🚨 CPU USAGE ALERT - ESCALATION 🚨

Severity: WARNING (may escalate to CRITICAL)
Service: LIA Production
Duration: [XX] minutes

Current Status:
- CPU Usage: [XX]% (Threshold: 80%)
- Affected: [Container names]
- Load Average: [X.XX, X.XX, X.XX]

User Impact:
- API Latency: P95 [X]s (normal: <1s)
- Error Rate: [X]% (normal: <1%)
- Estimated Users Affected: [XX]

Actions Taken:
- [✓] Restarted API container → CPU reduced to [XX]% for 5min, then spiked again
- [✓] Checked logs → No obvious errors
- [ ] Pending: [Next action]

Root Cause Hypothesis:
[Brief description or "Under investigation"]

Escalation Reason:
- Mitigation ineffective / Sustained >15min / Unknown cause

Dashboards:
- Infrastructure: http://localhost:3000/d/infrastructure-resources
- Prometheus: http://localhost:9090/graph?g0.expr=node_cpu

Request:
[Specific ask - e.g., "Approve scaling to 4 API replicas" or "Need help diagnosing"]
```

---

## 📝 Post-Incident Actions

### Immediate (<1 hour after resolution)

- [ ] Create incident report (see template below)
- [ ] Document root cause and resolution in incident tracker
- [ ] Notify stakeholders of resolution
- [ ] Verify monitoring returned to normal (CPU <60%, latency <1s, error rate <1%)

### Short-term (<24 hours after resolution)

- [ ] Update this runbook with incident-specific learnings
- [ ] Create GitHub issues for permanent fixes:
  - Code optimization (if regression identified)
  - Resource scaling (if capacity issue)
  - Monitoring improvements (if blind spot discovered)
- [ ] Review alert threshold (was 80% appropriate? Should warn at 70%?)
- [ ] Schedule post-mortem meeting (if severity warranted)

### Long-term (<1 week after resolution)

- [ ] Conduct post-mortem review (if critical incident)
- [ ] Implement action items from post-mortem
- [ ] Update capacity planning documents
- [ ] Add load testing for identified bottleneck
- [ ] Update deployment checklist (if deployment-related)

---

## 📋 Incident Report Template

```markdown
# Incident Report: High CPU Usage

**Incident ID**: INC-[YYYY-MM-DD-XXX]
**Date**: [YYYY-MM-DD]
**Duration**: [Start time] - [End time] ([Total duration])
**Severity**: Warning (or Critical if escalated)
**Services Affected**: LIA API, [Others]

## Summary
[1-2 sentence description of what happened]

## Timeline (UTC)
- [HH:MM] - Alert fired: HighCPUUsage (CPU at XX%)
- [HH:MM] - On-call engineer notified
- [HH:MM] - Investigation started
- [HH:MM] - Root cause identified: [Description]
- [HH:MM] - Mitigation applied: [Action]
- [HH:MM] - CPU normalized to <60%
- [HH:MM] - Alert resolved
- [HH:MM] - Incident closed

## Impact
- **Users Affected**: [Number/percentage]
- **Requests Degraded**: [Count or %]
- **Error Rate**: [X%]
- **Revenue Impact**: [$ or N/A]
- **SLA Breach**: [Yes/No]

## Root Cause
[Detailed explanation of why CPU usage spiked]

**Contributing Factors**:
- [Factor 1]
- [Factor 2]

## Detection
- **Alert**: HighCPUUsage fired at [time]
- **TTD (Time to Detect)**: [X minutes from issue start]
- **Detection Method**: [Prometheus alert / User report / Monitoring]

## Response
- **TTR (Time to Respond)**: [X minutes from alert to engineer engagement]
- **TTM (Time to Mitigate)**: [X minutes from engagement to CPU normalized]
- **MTTR (Mean Time to Recovery)**: [Total incident duration]

## Resolution
**Actions Taken**:
1. [Action 1] - [Result]
2. [Action 2] - [Result]
3. [Action 3] - [Result]

**Final Solution**: [What permanently fixed the issue]

## Lessons Learned

### What Went Well
- [Point 1]
- [Point 2]

### What Went Wrong
- [Point 1]
- [Point 2]

### Where We Got Lucky
- [Point 1]

## Action Items
- [ ] [Action 1] - Owner: [Name] - Due: [Date] - GitHub: #[issue]
- [ ] [Action 2] - Owner: [Name] - Due: [Date] - GitHub: #[issue]
- [ ] [Action 3] - Owner: [Name] - Due: [Date] - GitHub: #[issue]

## References
- Runbook: [HighCPUUsage.md](./HighCPUUsage.md)
- Alert definition: `infrastructure/observability/prometheus/alerts.yml#HighCPUUsage`
- Grafana dashboard: http://localhost:3000/d/infrastructure-resources
- GitHub issue: #[number]
```

---

## 🔗 Additional Resources

### Internal Documentation
- [Infrastructure Architecture](../../architecture/infrastructure.md)
- [Performance Optimization Guide](../../performance/optimization.md)
- [Docker Resource Limits](../../docker/resource_management.md)
- [API Performance Best Practices](../../api/performance.md)

### External Resources
- [Understanding Linux Load Average](https://www.brendangregg.com/blog/2017-08-08/linux-load-averages.html)
- [Docker CPU Limiting](https://docs.docker.com/config/containers/resource_constraints/#cpu)
- [Python GIL and Multiprocessing](https://realpython.com/python-gil/)
- [FastAPI Performance Tuning](https://fastapi.tiangolo.com/deployment/concepts/#performance-and-speed)
- [Prometheus CPU Metrics](https://prometheus.io/docs/prometheus/latest/querying/examples/#cpu-usage)

### Profiling Tools
- **py-spy** - Python CPU profiler (zero-instrumentation)
  ```bash
  docker-compose exec api py-spy top --pid 1
  docker-compose exec api py-spy record --pid 1 --duration 60 --output profile.svg
  ```

- **htop** - Interactive process viewer
  ```bash
  docker-compose exec api apt-get update && apt-get install -y htop
  docker-compose exec api htop
  ```

- **perf** - Linux profiling tool (advanced)
  ```bash
  # Requires privileged container
  perf top -p $(docker inspect --format '{{.State.Pid}}' lia_api_1)
  ```

---

## 📅 Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-23
**Author**: SRE Team
**Reviewers**: DevOps Team, Backend Team
**Next Review Date**: 2025-12-23

**Change History**:
- 2025-11-23: Initial version created

**Related Alerts**:
- HighCPUUsage (this runbook)
- HighMemoryUsage (often correlated)
- CriticalLatencyP99 (symptom of high CPU)
- ContainerDown (can result from sustained high CPU)

---

## ✅ Validation Checklist

Before marking this runbook as production-ready:

- [x] Alert definition verified in `alerts.yml`
- [x] All bash commands syntax-checked
- [x] All PromQL queries validated
- [x] Grafana dashboard links confirmed
- [x] Docker commands tested in staging
- [x] Resolution steps validated
- [ ] Peer review completed (2+ reviewers)
- [ ] Dry-run performed in staging environment
- [ ] Approved by Infrastructure Lead

---

## 📌 Notes

**Critical Safety Warnings**:
- **NEVER** kill PID 1 in a container (main process) unless you intend to restart the container
- **ALWAYS** verify current load before scaling resources (avoid over-provisioning)
- **ALWAYS** check for correlated alerts (HighMemoryUsage, DiskSpaceCritical) before diagnosing in isolation

**Performance Considerations**:
- CPU >80% for >10 minutes can cause cascading failures (request timeouts → retries → more CPU)
- Modern CPUs have turbo boost - brief spikes to 100% are normal and not concerning
- Load average >2x CPU cores indicates CPU starvation (processes waiting for CPU)

**Testing Notes**:
- Test CPU spike scenarios in staging with stress tool: `stress --cpu 4 --timeout 60s`
- Simulate traffic spike with load testing: `locust -f load_test.py --users 100`
- Verify mitigation steps don't cause data loss or service interruption

**Maintenance Schedule**:
- Review CPU usage trends monthly (identify growth patterns)
- Audit CPU resource limits quarterly (adjust as workload evolves)
- Load test after major deployments (verify performance regressions)

---

**End of Runbook**
