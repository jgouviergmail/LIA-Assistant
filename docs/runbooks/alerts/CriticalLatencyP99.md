# CriticalLatencyP99 - Runbook

**Severity**: critical
**Component**: api
**Impact**: UX sévèrement dégradée, timeouts utilisateurs, SLA breach, risque d'abandon
**SLA Impact**: Yes - Breaches latency SLA (target: P99 <1s for API, <2s for agents)

---

## 📊 Alert Definition

**Alert Name**: `CriticalLatencyP99`

**Prometheus Expression**:
```promql
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service)
) > <<< ALERT_API_LATENCY_P99_CRITICAL_SECONDS >>>
```

**Threshold**:
- **Production**: 1.5s (stricter than default 2s - early detection)
- **Staging**: 3s (relaxed for test environment)
- **Development**: 10s (very relaxed - debugging, breakpoints acceptable)

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: critical
- `component`: api
- `service`: [service name from metric]

**Related Alerts**:
- `HighLatencyP95` (warning at lower percentile/threshold)
- `HighErrorRate` (often correlated - slow → timeout → error)

---

## 🔍 Symptoms

### What Users See
- Pages chargent très lentement (>5 secondes)
- Spinners tournent indéfiniment
- Timeouts fréquents (30-60s puis erreur)
- Conversations agents bloquent à "Thinking..."
- Recherches contacts/emails ne retournent pas résultats
- Utilisateurs abandonnent avant fin chargement
- Messages "Request timeout" dans interface

### What Ops See
- Métrique `http_request_duration_seconds` P99 >2s dans Prometheus
- Alert `CriticalLatencyP99` firing dans AlertManager
- Souvent co-firing avec `HighLatencyP95`, `AgentsRouterLatencyHigh`
- Grafana panels "API Latency" tous en rouge/orange
- Logs API: Requêtes individuelles loggées avec `duration: 5.2s`
- APM/tracing montre slow spans (DB queries, LLM calls, external APIs)
- Users actifs en baisse (abandons)

---

## 🎯 Possible Causes

### 1. Database Slow Queries / Missing Indexes

**Likelihood**: **High** (cause #1 la plus fréquente)

**Description**:
Queries SQL lentes bloquent requests. Souvent causé par:
- Missing indexes (full table scans)
- N+1 query problem (ORM fetching sans eager loading)
- Unoptimized JOINs
- Large OFFSET pagination
- Locks/deadlocks

SQLAlchemy ORM peut générer queries inefficientes si mal utilisé.

**How to Verify**:
```bash
# 1. Identifier slow queries actives
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  now() - query_start as duration,
  state,
  substring(query, 1, 200) as query_preview
FROM pg_stat_activity
WHERE datname='lia'
  AND state = 'active'
  AND now() - query_start > interval '1 second'
ORDER BY query_start ASC
LIMIT 15;
"

# 2. Analyser slow queries log (si pg_stat_statements activé)
docker-compose exec postgres psql -U lia -c "
SELECT
  calls,
  mean_exec_time,
  max_exec_time,
  substring(query, 1, 150) as query_preview
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname='lia')
  AND mean_exec_time > 1000  -- >1s mean
ORDER BY mean_exec_time DESC
LIMIT 10;
"

# 3. Chercher N+1 patterns dans logs API
docker-compose logs api --since=15m | grep "SELECT" | wc -l
# Si >1000 SELECTs en 15min → probable N+1

# 4. Vérifier explain plan pour query suspecte
docker-compose exec postgres psql -U lia -c "
EXPLAIN ANALYZE
SELECT * FROM conversations WHERE user_id = 123 ORDER BY created_at DESC LIMIT 10;
"
# Chercher "Seq Scan" (bad) vs "Index Scan" (good)
```

**Expected Output if This is the Cause**:
```
# Queries >5s actives
 pid  | duration  | state  | query_preview
------+-----------+--------+------------------------
 9876 | 00:00:08  | active | SELECT c.*, m.* FROM conversations c LEFT JOIN messages m...

# pg_stat_statements montre queries lentes
 calls | mean_exec_time | max_exec_time | query_preview
-------+----------------+---------------+------------------
   234 |        4523.21 |      12456.78 | SELECT * FROM conversations WHERE...

# EXPLAIN montre Seq Scan (pas d'index)
Seq Scan on conversations  (cost=0.00..1234.56 rows=10000 width=512)
  Filter: (user_id = 123)
```

---

### 2. LLM API Latency (Anthropic Claude)

**Likelihood**: **High** (pour endpoints agents)

**Description**:
Anthropic Claude API peut prendre 5-30s pour générer réponses, surtout:
- Large context (>50K tokens input)
- Long completions (max_tokens élevé)
- Anthropic sous charge (peak hours US)
- Streaming disabled (wait for full response)

LIA agents dépendent de Claude → latency API se propage à user.

**How to Verify**:
```bash
# 1. Vérifier latency LLM API actuelle
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'

# 2. Comparer latency API vs agent endpoints
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket{path=~\"/api/agents/.*\"}[5m]))by(le))" | jq '.data.result[0].value[1]'

# 3. Vérifier logs pour slow LLM calls
docker-compose logs api --since=30m | grep -i "anthropic\|claude" | grep -oP "duration: \K[0-9.]+" | sort -rn | head -10

# 4. Check token counts (high tokens = high latency)
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(llm_tokens_total_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'

# 5. Vérifier si streaming enabled
docker-compose logs api | grep -c "stream=True"
```

**Expected Output if This is the Cause**:
```
# LLM P99 latency très élevé
"15.3"  # 15s!

# Agent endpoints latency corrélée
"16.8"  # API latency ≈ LLM latency + overhead

# Logs montrent slow calls
12.4
8.9
7.2
...

# Token counts élevés
"75000"  # 75K tokens input
```

---

### 3. External API Timeouts / Slow Dependencies

**Likelihood**: **Medium**

**Description**:
Dépendances externes lentes:
- Google APIs (Contacts, Gmail) timeout ou slow
- OAuth provider callbacks lents
- Redis slow (network, memory pressure)
- DNS resolution lent

**How to Verify**:
```bash
# 1. Tester Redis latency
docker-compose exec redis redis-cli --latency-history

# 2. Vérifier logs pour external API timeouts
docker-compose logs api --since=30m | grep -i "timeout\|external\|google\|oauth" | grep -v "LLM"

# 3. Test DNS resolution speed
docker-compose exec api time nslookup accounts.google.com

# 4. Vérifier métriques external calls si instrumentées
curl -s "http://localhost:9090/api/v1/query?query=http_external_request_duration_seconds" | jq '.data.result'

# 5. Test connectivity vers Google APIs
docker-compose exec api curl -w "@-" -o /dev/null -s "https://www.googleapis.com/auth/userinfo.email" <<< 'time_total: %{time_total}\n'
```

**Expected Output if This is the Cause**:
```
# Redis latency spikes
min: 0, max: 1500, avg: 234.12 (1500ms max!)

# Timeouts dans logs
2025-11-22 14:32:15 ERROR: Google API timeout after 10s
httpx.TimeoutException: Request to https://www.googleapis.com/gmail/v1/...

# DNS slow
real    0m3.245s  # 3s pour DNS!

# External API slow
time_total: 5.234
```

---

### 4. High CPU / Memory Pressure

**Likelihood**: **Medium**

**Description**:
Ressources CPU/memory saturées ralentissent processing:
- CPU 100% → context switching, slow computation
- Memory swapping → disk I/O extreme slow
- Python GC pauses (large objects, memory leaks)
- Container throttling (CPU limits atteints)

**How to Verify**:
```bash
# 1. Vérifier CPU/memory usage containers
docker stats --no-stream

# 2. Vérifier CPU system-wide
top -bn1 | head -20

# 3. Vérifier si swapping actif
free -h
vmstat 1 5

# 4. Vérifier métriques Prometheus
curl -s "http://localhost:9090/api/v1/query?query=rate(container_cpu_usage_seconds_total{name=\"lia_api\"}[5m])*100" | jq '.data.result[0].value[1]'

# 5. Vérifier Python GC dans logs
docker-compose logs api | grep -i "garbage collection\|gc"
```

**Expected Output if This is the Cause**:
```
# docker stats montre saturation
CONTAINER  CPU %   MEM USAGE / LIMIT     MEM %
api        198%    1.9GiB / 2GiB        95%

# top montre load average élevé
load average: 8.23, 7.45, 6.89  # Sur 4 CPUs = 2x overload

# Swapping actif
Swap:     4.0Gi   2.3Gi   1.7Gi  # 2.3GB swap used!

# CPU >100% (throttling)
"198.5"
```

---

### 5. Synchronous Blocking Operations

**Likelihood**: **Medium**

**Description**:
Code synchrone bloquant event loop async:
- File I/O synchrone (large file reads/writes)
- Synchronous HTTP calls dans async context
- Heavy computation sans offloading
- Checkpoint serialization bloquante (LangGraph)

FastAPI async routes bloquées par sync operations causent latency globale.

**How to Verify**:
```bash
# 1. Chercher warnings async dans logs
docker-compose logs api --since=30m | grep -i "blocking\|sync\|event loop\|coroutine"

# 2. Profile code avec py-spy (si installé)
docker-compose exec api py-spy top --pid 1

# 3. Vérifier checkpoint save duration
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(checkpoint_save_duration_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'

# 4. Analyser stack traces si slow request log
docker-compose logs api | grep -A 20 "Slow request"
```

**Expected Output if This is the Cause**:
```
# Warnings dans logs
WARNING: Detected blocking call in async context
  File "/app/src/domains/agents/nodes/router.py", line 123
    result = requests.get(url)  # Synchronous!

# Checkpoint save lent
"3.5"  # 3.5s pour save checkpoint

# Stack trace montre blocking I/O
File "/usr/local/lib/python3.11/json/__init__.py", line 231, in dump
  # Large JSON serialization blocking
```

---

## 🔧 Diagnostic Steps

### Quick Health Check (< 2 minutes)

**Objectif**: Identifier rapidement composant lent.

```bash
# 1. Vérifier latency actuelle P99
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'

# 2. Breakdown latency par endpoint
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le,path))" | jq '.data.result[] | {path: .metric.path, p99: .value[1]}'

# 3. Vérifier slow queries DB
docker-compose exec postgres psql -U lia -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lia' AND state='active' AND now()-query_start > interval '2 seconds';"

# 4. Vérifier LLM latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'

# 5. Check CPU/memory
docker stats --no-stream api | tail -1
```

**Interprétation**:
- Si P99 >5s: Critique, mitigation immédiate
- Si endpoint spécifique >>autres: Problème localisé à cet endpoint
- Si DB slow queries >5: Probable cause DB
- Si LLM latency >10s: Anthropic API slow
- Si CPU >150% ou MEM >90%: Resource pressure

---

### Deep Dive Investigation (5-10 minutes)

#### Step 1: Identifier Top Slow Endpoints
```bash
# Top 5 endpoints par latency P99
curl -s "http://localhost:9090/api/v1/query?query=topk(5,histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le,path)))" | jq '.data.result[] | {path: .metric.path, p99_seconds: .value[1]}'
```

---

#### Step 2: Analyser Slow Endpoint Détaillé

**Si endpoint agents lent**:
```bash
# Breakdown agents latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(agent_router_latency_seconds_bucket[5m]))by(le))" | jq .
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq .

# Si router + LLM lents → problème agents
```

**Si endpoint DB-heavy lent**:
```bash
# Identifier queries lentes pour cet endpoint
docker-compose logs api --since=30m | grep "GET /api/[endpoint]" | grep -oP "duration: \K[0-9.]+" | sort -rn | head -10

# Puis analyser query patterns
docker-compose exec postgres psql -U lia -c "SELECT query FROM pg_stat_activity WHERE state='active' AND query LIKE '%[table_suspect]%';"
```

---

#### Step 3: Distributed Tracing (si OpenTelemetry configuré)

```bash
# Vérifier traces pour request lente
# (dépend de setup - Jaeger, Zipkin, etc.)

# Analyser span breakdown:
# - DB query spans
# - LLM API call spans
# - External API spans
# - Business logic spans
```

---

#### Step 4: Profiling Code

**Si cause non évidente**:
```bash
# Install py-spy in container (si pas déjà fait)
docker-compose exec api pip install py-spy

# Profile pendant 30s
docker-compose exec api py-spy record -o /tmp/profile.svg --pid 1 --duration 30

# Copier profile pour analyse
docker cp lia_api:/tmp/profile.svg ./profile.svg

# Ouvrir profile.svg dans browser pour voir flamegraph
```

---

### Automated Diagnostic Script

```bash
infrastructure/observability/scripts/diagnose_api_latency.sh
```

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding)

#### Option A: Add Missing Database Indexes (5 minutes)

**Use When**: Slow queries identifiées, missing indexes détectés.

```sql
-- Identifier tables sans index sur foreign keys
SELECT
  schemaname,
  tablename,
  attname,
  n_distinct
FROM pg_stats
WHERE schemaname = 'public'
  AND n_distinct > 100
  AND (schemaname, tablename, attname) NOT IN (
    SELECT schemaname, tablename, attname
    FROM pg_stats s
    JOIN pg_index i ON s.tablename::regclass = i.indrelid
  );

-- Créer indexes CONCURRENTLY (production safe)
CREATE INDEX CONCURRENTLY idx_conversations_user_id ON conversations(user_id);
CREATE INDEX CONCURRENTLY idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX CONCURRENTLY idx_checkpoints_conversation_id_created ON checkpoints(conversation_id, created_at DESC);
```

**Deploy**:
```bash
# Apply migrations
docker-compose exec postgres psql -U lia < add_indexes.sql

# Verify indexes created
docker-compose exec postgres psql -U lia -c "\d+ conversations"
```

**Pros**: Fix permanent, amélioration immédiate, no downtime
**Cons**: Index creation peut prendre temps sur large tables
**Duration**: 2-10 minutes selon table size

---

#### Option B: Enable LLM Streaming (10 minutes)

**Use When**: LLM latency identifié comme cause, streaming pas activé.

```python
# apps/api/src/infrastructure/llm/anthropic_client.py

# Avant
response = await client.messages.create(
    model="claude-3-sonnet-20240229",
    messages=messages,
    max_tokens=2000,
    stream=False  # User attend 10s pour réponse complète
)

# Après
async def stream_response(messages):
    async with client.messages.stream(
        model="claude-3-sonnet-20240229",
        messages=messages,
        max_tokens=2000
    ) as stream:
        async for text in stream.text_stream:
            yield text  # User voit tokens progressivement (TTFT <1s)
```

**Pros**: TTFT réduit de 10s → <1s, meilleure UX perçue
**Cons**: Code changes required, need SSE support frontend
**Duration**: 10 minutes code + test

---

#### Option C: Implement Caching for Expensive Operations (15 minutes)

**Use When**: Repeated queries/computations identifiées.

```python
# apps/api/src/domains/agents/cache.py
from functools import lru_cache
import redis

redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

@lru_cache(maxsize=1000)
def get_user_contacts(user_id: int):
    # Cache en mémoire pour requests multiples même user
    ...

async def get_contact_with_cache(contact_id: int):
    # Cache Redis pour cross-request
    cache_key = f"contact:{contact_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    contact = await fetch_contact(contact_id)
    redis_client.setex(cache_key, 3600, json.dumps(contact))  # TTL 1h
    return contact
```

**Pros**: Réduction latency 10x+ pour cached data
**Cons**: Cache invalidation complexity, stale data risk
**Duration**: 15 minutes

---

#### Option D: Increase Container Resources (2 minutes)

**Use When**: CPU/memory saturation identifié.

```yaml
# docker-compose.yml
services:
  api:
    # Avant
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G

    # Après
    deploy:
      resources:
        limits:
          cpus: '4'      # 2x CPU
          memory: 4G     # 2x memory
```

**Deploy**:
```bash
docker-compose down api
docker-compose up -d api
```

**Pros**: Fix immédiat si resources insuffisantes
**Cons**: Coût infrastructure, pas sustainable long-term
**Duration**: 2 minutes

---

#### Option E: Offload Heavy Computation to Background Workers

**Use When**: Synchronous blocking operations identifiées.

```python
# Avant - Blocking
async def process_conversation(conversation_id: int):
    # Heavy synchronous computation blocks event loop
    result = heavy_computation(conversation_id)  # 5s blocking!
    return result

# Après - Async queue
from celery import Celery
celery_app = Celery('tasks', broker='redis://redis:6379/0')

@celery_app.task
def heavy_computation_task(conversation_id: int):
    return heavy_computation(conversation_id)

async def process_conversation(conversation_id: int):
    # Enqueue task, return immediately
    task = heavy_computation_task.delay(conversation_id)
    return {"task_id": task.id, "status": "processing"}
```

**Pros**: Event loop non-bloqué, latency API <100ms
**Cons**: Async UX (polling/webhooks needed), infrastructure complexity
**Duration**: 30 minutes

---

### Verification After Mitigation

```bash
# 1. Vérifier alert cleared
watch -n 10 'curl -s http://localhost:9093/api/v2/alerts | jq ".[] | select(.labels.alertname==\"CriticalLatencyP99\") | .status.state"'

# 2. Vérifier P99 latency diminue
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'

# 3. Test fonctionnel endpoints
curl -w "@-" -o /dev/null "http://localhost:8000/api/agents/chat" -X POST -H "Content-Type: application/json" -d '{"query":"test"}' <<< 'time_total: %{time_total}\n'

# 4. Vérifier percentiles autres
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.50,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'  # P50
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'  # P95
```

**Expected After Success**:
- P99 <1.5s (production threshold)
- P95 <1s
- P50 <300ms
- Alert inactive
- No slow queries >2s

---

### Root Cause Fix (Permanent Solution)

#### If Cause = Missing Indexes

**Permanent**: Database migration avec tous indexes nécessaires.

```python
# Migration file: add_performance_indexes.py
"""Add indexes for performance optimization."""

def upgrade():
    # Foreign key indexes
    op.create_index('idx_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('idx_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('idx_checkpoints_conversation_id', 'checkpoints', ['conversation_id'])

    # Composite indexes pour queries fréquentes
    op.create_index(
        'idx_conversations_user_created',
        'conversations',
        ['user_id', 'created_at DESC']
    )

    # Partial index pour queries filtered
    op.execute("""
        CREATE INDEX idx_conversations_active
        ON conversations (user_id, updated_at DESC)
        WHERE status = 'active';
    """)

def downgrade():
    op.drop_index('idx_conversations_user_id')
    ...
```

---

#### If Cause = N+1 Queries

**Fix**: Eager loading avec SQLAlchemy.

```python
# Avant - N+1
conversations = session.query(Conversation).filter_by(user_id=123).all()
for conv in conversations:
    messages = conv.messages  # N queries!

# Après - Eager loading
from sqlalchemy.orm import joinedload

conversations = (
    session.query(Conversation)
    .filter_by(user_id=123)
    .options(joinedload(Conversation.messages))  # 1 query avec JOIN
    .all()
)
```

---

#### If Cause = LLM Latency

**Permanent**:
- Enable streaming (TTFT optimization)
- Reduce context size (trim old messages)
- Use faster model for simple queries (Haiku vs Sonnet)
- Implement result caching

```python
def select_model_by_complexity(query: str) -> str:
    """Use appropriate model based on query complexity."""
    if len(query) < 100 and is_simple_query(query):
        return "claude-3-haiku-20240307"  # Fast, cheap
    else:
        return "claude-3-sonnet-20240229"  # Slower, smarter
```

---

#### Monitoring Post-Fix

**Surveiller 48-72h**:
- P99 reste <1s
- P95 <500ms
- P50 <200ms
- No regressions
- User satisfaction metrics (si disponibles)

```bash
# Continuous monitoring query
watch -n 60 'curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq -r ".data.result[0].value[1] | tonumber | if . > 1.5 then \"ALERT: P99 = \" + (. | tostring) + \"s\" else \"OK: P99 = \" + (. | tostring) + \"s\" end"'
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **API Performance**: `http://localhost:3000/d/api-performance`
  - Panel: "Latency Percentiles (P50/P95/P99)"
  - Panel: "Slow Requests by Endpoint"
- **Database Performance**: `http://localhost:3000/d/postgres`
  - Panel: "Slow Queries"
  - Panel: "Query Duration Distribution"

### Prometheus Queries
```promql
# P99 latency
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# P99 by endpoint
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, path))

# Latency distribution
sum(rate(http_request_duration_seconds_bucket[5m])) by (le)

# Slow requests count (>2s)
sum(rate(http_request_duration_seconds_count{le="2"}[5m]))
```

---

## 📚 Related Runbooks

- **[HighLatencyP95](./HighLatencyP95.md)** - Warning précurseur
- **[HighErrorRate](./HighErrorRate.md)** - Timeouts → errors
- **[CriticalDatabaseConnections](./CriticalDatabaseConnections.md)** - DB slowness cause
- **[LLMAPIFailureRateHigh](./LLMAPIFailureRateHigh.md)** - LLM latency cause
- **[AgentsRouterLatencyHigh](./AgentsRouterLatencyHigh.md)** - Agents-specific latency

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Morning Spike (Cold Start)
**Description**: Premier traffic matin → caches froids → slow
**Resolution**: Cache pre-warming cron job
**Prevention**: Keep-alive requests, persistent connections

### Pattern 2: Pagination Death Spiral
**Description**: Large OFFSET pagination (page 1000+) = full table scan
**Resolution**: Cursor-based pagination
**Prevention**: Limit max page, use keyset pagination

### Known Issue 1: Checkpoint Serialization Blocking
**Symptom**: Agent responses freeze 2-3s périodiquement
**Workaround**: Offload checkpoint save to background
**Tracking**: GitHub issue #[TODO]

### Known Issue 2: LLM Streaming Not Implemented Everywhere
**Symptom**: Some agent endpoints still wait full response
**Workaround**: Enable streaming endpoint by endpoint
**Tracking**: GitHub issue #[TODO]

---

## 🆘 Escalation

### When to Escalate

Escalader si:
- [ ] P99 >10s pendant 15+ minutes
- [ ] Mitigation failed après 3 tentatives
- [ ] Impact >500 users actifs
- [ ] Revenue-impacting (checkout, critical feature)
- [ ] Root cause requires architectural change

### Escalation Path

**Level 1 - Senior Backend Engineer** (0-15min):
- **Contact**: Backend Lead
- **Slack**: #backend-critical

**Level 2 - Architect / Performance Engineer** (15-30min):
- **Contact**: Tech Lead / Architect
- **Decision needed**: Caching strategy, architecture changes

**Level 3 - CTO** (30min+):
- **Contact**: CTO
- **Decision needed**: Infrastructure scaling, budget for optimization

---

## 📝 Post-Incident Actions

### Immediate (<1h)
- [ ] Create incident report
- [ ] Identify exact slow component (DB/LLM/code)
- [ ] Document latency timeline
- [ ] Capture traces/profiles

### Short-Term (<24h)
- [ ] Update runbook
- [ ] Add missing indexes if DB cause
- [ ] Implement caching if applicable
- [ ] Add monitoring gaps (per-endpoint P99, slow query alerts)

### Long-Term (<1 week)
- [ ] Post-mortem
- [ ] Performance testing régulier
- [ ] APM/tracing deployment si manquant
- [ ] Query optimization review
- [ ] Consider CDN/edge caching

---

## 🔗 Additional Resources

### Documentation
- [FastAPI Performance Tips](https://fastapi.tiangolo.com/advanced/performance/)
- [PostgreSQL Query Optimization](https://www.postgresql.org/docs/current/performance-tips.html)
- [SQLAlchemy Performance](https://docs.sqlalchemy.org/en/20/faq/performance.html)

### Code References
- API Routes: `apps/api/src/main.py`
- Database Queries: `apps/api/src/domains/*/models.py`
- LLM Client: `apps/api/src/infrastructure/llm/anthropic_client.py`

### Tools
- [py-spy](https://github.com/benfred/py-spy) - Python profiler
- [pgBadger](https://github.com/darold/pgbadger) - PostgreSQL log analyzer
- [OpenTelemetry](https://opentelemetry.io/) - Distributed tracing

---

## 📅 Runbook Metadata

**Created**: 2025-11-22
**Last Updated**: 2025-11-22
**Maintainer**: Backend Team + Performance Engineering
**Version**: 1.0
**Related GitHub Issues**: #31

---

## ✅ Runbook Validation Checklist

- [x] Alert definition verified
- [ ] Queries tested in staging (**TODO**)
- [ ] Profiling tools installed (**TODO**)
- [ ] APM/tracing setup reviewed (**TODO**)
- [ ] Performance benchmarks established (**TODO**)
- [ ] Caching strategy documented (**TODO**)

---

**Note**: Latency issues sont souvent multi-causales. Utiliser diagnostic systématique (DB + LLM + code + infrastructure) pour identifier toutes les causes.
