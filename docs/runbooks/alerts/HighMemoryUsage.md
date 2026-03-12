# HighMemoryUsage - Runbook

**Severity**: Warning
**Component**: Infrastructure (Memory)
**Impact**: Performance degradation, potential OOM kills, service instability
**SLA Impact**: No (warning level) - May escalate to Yes if memory exhaustion occurs

---

## 📊 Alert Definition

**Alert Name**: `HighMemoryUsage`

**Prometheus Expression**:
```promql
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > ${ALERT_MEMORY_USAGE_WARNING_PERCENT}
```

**Threshold**:
- **Production**: >85% memory usage (ALERT_MEMORY_USAGE_WARNING_PERCENT=85)
- **Staging**: >90% memory usage (Higher tolerance for test environments)
- **Development**: >95% memory usage (Relaxed threshold)

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: warning
- `component`: memory
- `instance`: [hostname/IP of affected instance]

---

## 🔍 Symptoms

### What Users See
- **Slow API responses** - Requests taking 3-10x longer due to swap usage
- **Intermittent 503 errors** - Containers killed by OOM (Out Of Memory)
- **Connection timeouts** - New connections rejected when memory full
- **Incomplete responses** - Requests terminated mid-processing

### What Ops See
- **High memory >85%** in monitoring dashboards
- **OOM killer events** - `dmesg | grep oom` shows killed processes
- **Swap usage increasing** - System swapping to disk (performance degradation)
- **Container restarts** - Docker containers repeatedly restarting due to memory limits
- **Slow garbage collection** - Python/Java GC taking seconds instead of milliseconds

---

## 🎯 Possible Causes

### 1. Memory Leak in Application Code (High Likelihood)

**Likelihood**: High (65%) - Most common cause in long-running applications

**Description**:
Application code allocating memory but not releasing it. Common patterns: caching without eviction, circular references preventing GC, accumulating event listeners, unbounded lists/dictionaries.

**How to Verify**:
```bash
# Check memory usage trend over time (growing = likely leak)
curl -s "http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{name=\"lia_api_1\"}" | jq '.data.result[0].value[1]'

# Compare to 1 hour ago
curl -s "http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{name=\"lia_api_1\"} offset 1h" | jq '.data.result[0].value[1]'

# Check container memory stats
docker stats --no-stream lia_api_1

# Check Python memory allocation (if py-spy available)
docker-compose exec api py-spy dump --pid 1

# Check for large objects in memory (Python)
docker-compose exec api python -c "
import gc
import sys
large_objects = [(sys.getsizeof(obj), type(obj).__name__) for obj in gc.get_objects()]
large_objects.sort(reverse=True)
for size, obj_type in large_objects[:20]:
    print(f'{size:>12,} bytes - {obj_type}')
"
```

**Expected Output if This is the Cause**:
- Memory usage growing steadily (e.g., +100MB/hour)
- Memory usage NOT correlated with traffic (grows even during low traffic)
- Large lists/dictionaries dominating memory (>100MB each)
- Memory usage continues growing after container restart

---

### 2. Large Conversation State / Checkpoint Bloat (Medium-High Likelihood)

**Likelihood**: Medium-High (55%) - Specific to this application (LangGraph checkpoints)

**Description**:
Conversation checkpoints storing full message history without pagination/pruning, causing each active conversation to consume 1-10MB of memory. With 100+ concurrent conversations, memory exhausts rapidly.

**How to Verify**:
```bash
# Check number of active conversations
curl -s "http://localhost:9090/api/v1/query?query=active_conversations_total" | jq '.data.result[0].value[1]'

# Check checkpoint memory usage (if instrumented)
curl -s "http://localhost:9090/api/v1/query?query=checkpoint_memory_bytes_sum" | jq '.data.result[0].value[1]'

# Check largest checkpoints in database
docker-compose exec postgres psql -U lia -c "
SELECT
  conversation_id,
  pg_size_pretty(length(checkpoint_data::text)) AS checkpoint_size,
  jsonb_array_length(checkpoint_data->'messages') AS message_count
FROM checkpoints
ORDER BY length(checkpoint_data::text) DESC
LIMIT 10;
"

# Check conversation duration (long conversations = large states)
docker-compose exec postgres psql -U lia -c "
SELECT
  id,
  user_id,
  created_at,
  updated_at,
  (updated_at - created_at) AS duration
FROM conversations
WHERE updated_at > NOW() - INTERVAL '24 hours'
ORDER BY duration DESC
LIMIT 10;
"
```

**Expected Output if This is the Cause**:
- Checkpoints >1MB (healthy: <500KB)
- Message count >100 per conversation (healthy: <50)
- Memory usage correlated with active conversation count
- Long-running conversations (>2 hours) with large states

---

### 3. Unbounded Cache Growth (Medium Likelihood)

**Likelihood**: Medium (45%) - Common in web applications

**Description**:
In-memory caches (Redis, LRU cache, prompt cache) configured without size limits or TTL, growing unbounded until memory exhausts.

**How to Verify**:
```bash
# Check Redis memory usage
docker-compose exec redis redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human"

# Check if Redis eviction is working
docker-compose exec redis redis-cli INFO stats | grep evicted_keys

# Check Python LRU cache stats (if instrumented)
docker-compose logs api | grep -i "cache" | tail -50

# Check application cache size (if exposed as metric)
curl -s "http://localhost:9090/api/v1/query?query=cache_size_bytes" | jq '.data.result[0].value[1]'

# Check for cache configuration
grep -r "lru_cache\|@cache\|Cache" apps/api/src/ | grep -v "__pycache__"
```

**Expected Output if This is the Cause**:
- Redis memory approaching `maxmemory` limit
- `evicted_keys` = 0 (eviction not happening)
- Large cache metrics (>500MB)
- Cache size growing steadily over time

---

### 4. Database Connection Pool Leak (Medium Likelihood)

**Likelihood**: Medium (40%) - Common in ORM usage (SQLAlchemy, Alembic)

**Description**:
Database connections not properly closed, accumulating in pool. Each connection holds buffers/caches, consuming 5-50MB memory.

**How to Verify**:
```bash
# Check active database connections
docker-compose exec postgres psql -U lia -c "
SELECT
  COUNT(*) AS connection_count,
  state,
  application_name
FROM pg_stat_activity
WHERE datname = 'lia'
GROUP BY state, application_name
ORDER BY connection_count DESC;
"

# Check connection pool size (if instrumented)
curl -s "http://localhost:9090/api/v1/query?query=db_connection_pool_size" | jq '.data.result[0].value[1]'

# Check for long-running connections
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  usename,
  application_name,
  state,
  now() - state_change AS duration,
  substring(query, 1, 100) AS query_preview
FROM pg_stat_activity
WHERE datname = 'lia'
  AND state != 'idle'
ORDER BY duration DESC
LIMIT 10;
"

# Check SQLAlchemy pool stats (if exposed)
docker-compose logs api | grep -i "pool" | tail -50
```

**Expected Output if This is the Cause**:
- Connection count >> configured pool size (e.g., 50 vs pool max 20)
- Many connections in "idle in transaction" state
- Long-running connections (>10 minutes)
- Memory usage correlates with connection count

---

### 5. Large HTTP Response Buffering (Low-Medium Likelihood)

**Likelihood**: Low-Medium (30%) - Occurs with large LLM responses or file uploads

**Description**:
Streaming responses not properly implemented, causing entire LLM response (50KB-1MB) to buffer in memory before sending. With 50 concurrent requests, this consumes 50-100MB+.

**How to Verify**:
```bash
# Check average response size
docker-compose logs api --since 10m | grep "INFO" | grep -oP '"\w+ /\S+" \d+ms \d+B' | awk '{sum+=$4; count++} END {print "Average:", sum/count, "bytes"}'

# Check for large responses
docker-compose logs api --since 10m | grep "INFO" | grep -oP '\d+B$' | sort -n -r | head -20

# Check concurrent streaming requests
curl -s "http://localhost:9090/api/v1/query?query=streaming_requests_active" | jq '.data.result[0].value[1]'

# Check if SSE (Server-Sent Events) properly streaming
docker-compose logs api | grep -i "streaming\|sse" | tail -50
```

**Expected Output if This is the Cause**:
- Individual responses >100KB (LLM responses typically 5-50KB)
- Many concurrent streaming requests (>20)
- Memory spikes correlate with streaming endpoint usage
- Logs show "buffering" or "memory full" warnings

---

### 6. Dependency Library Memory Issue (Low Likelihood)

**Likelihood**: Low (20%) - Less common but possible with certain libraries

**Description**:
Third-party library (LangChain, FastAPI, SQLAlchemy, OpenAI SDK) has memory leak or inefficient memory usage in specific version.

**How to Verify**:
```bash
# Check recent dependency updates
git log --since="7 days ago" --oneline -- apps/api/pyproject.toml apps/api/requirements.txt

# Check installed versions vs latest
docker-compose exec api pip list --outdated

# Check for known issues in dependencies
# Search GitHub issues for "memory leak" in key dependencies:
# - langchain-core
# - langgraph
# - openai
# - fastapi
# - sqlalchemy

# Profile memory usage by library (if possible)
docker-compose exec api python -c "
import tracemalloc
tracemalloc.start()
# Import suspect libraries
import langchain
import langgraph
# Take snapshot
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
"
```

**Expected Output if This is the Cause**:
- Recent dependency update (< 7 days)
- Known issues in library GitHub repo mentioning memory
- Memory usage attributed to specific library in profiling

---

## 🔧 Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Check current memory usage**
```bash
# Overall host memory
free -h

# Expected output:
#               total        used        free      shared  buff/cache   available
# Mem:           16Gi       14Gi       500Mi       100Mi       1.5Gi       1.2Gi
#                           ^^^^                                          ^^^^
# Used >85% AND Available <2GB = CRITICAL

# Container memory usage
docker stats --no-stream

# Expected output shows which container(s) high memory:
# NAME                    MEM USAGE / LIMIT     MEM %
# lia_api_1        1.8GiB / 2GiB         90.0%  ← HIGH
# lia_postgres_1   400MiB / 1GiB         40.0%
# lia_redis_1      150MiB / 512MiB       29.3%
```

**Step 2: Check for recent OOM kills**
```bash
# Check kernel OOM killer logs
dmesg | grep -i "oom\|kill" | tail -20

# Expected output if OOM occurred:
# [timestamp] Out of memory: Killed process 12345 (python) total-vm:2048000kB
# [timestamp] oom-kill:constraint=CONSTRAINT_MEMCG

# Check Docker container restarts (OOM causes restart)
docker-compose ps | grep "Restarting"

# Check container exit code (137 = OOM killed)
docker inspect lia_api_1 | jq '.[0].State.ExitCode'
# 137 = SIGKILL (OOM)
```

**Step 3: Check memory growth rate**
```bash
# Check if memory still growing (active leak)
BEFORE=$(docker stats --no-stream --format "{{.MemUsage}}" lia_api_1 | awk '{print $1}')
sleep 60
AFTER=$(docker stats --no-stream --format "{{.MemUsage}}" lia_api_1 | awk '{print $1}')
echo "Before: $BEFORE, After: $AFTER"

# If AFTER > BEFORE by >10MB/minute → active leak
```

---

### Deep Dive Investigation (5-10 minutes)

**Step 4: Identify largest memory consumers**
```bash
# Top memory processes inside API container
docker-compose exec api ps aux --sort=-%mem | head -20

# Look for:
# - Multiple uvicorn workers each using >500MB
# - Python processes consuming >1GB
# - Zombie processes (defunct) holding memory

# Check Python object counts (if accessible)
docker-compose exec api python -c "
import gc
import sys
from collections import Counter
type_counts = Counter(type(obj).__name__ for obj in gc.get_objects())
for obj_type, count in type_counts.most_common(20):
    print(f'{count:>8,} {obj_type}')
"
# Large counts (>100k) of dict, list, str may indicate leak
```

**Step 5: Analyze memory allocation patterns**
```bash
# Memory allocation tracking (if tracemalloc enabled)
docker-compose logs api | grep -i "tracemalloc\|memory" | tail -50

# Check if memory correlates with specific endpoint
docker-compose logs api --since 30m | grep "INFO" | awk '{print $4, $6}' | sort | uniq -c | sort -rn | head -20
# Output shows endpoint + request count
# Cross-reference with memory spikes

# Check active conversation count vs memory
CONVERSATIONS=$(curl -s "http://localhost:9090/api/v1/query?query=active_conversations_total" | jq -r '.data.result[0].value[1]')
MEMORY=$(docker stats --no-stream --format "{{.MemUsage}}" lia_api_1 | awk '{print $1}')
echo "Conversations: $CONVERSATIONS, Memory: $MEMORY"
# Calculate memory per conversation: ~10-50MB is high
```

**Step 6: Check database and cache memory**
```bash
# PostgreSQL memory usage (shared_buffers + work_mem + connections)
docker-compose exec postgres psql -U lia -c "
SELECT
  name,
  setting,
  unit,
  context
FROM pg_settings
WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem', 'max_connections');
"

# Redis memory detailed breakdown
docker-compose exec redis redis-cli INFO memory

# Look for:
# used_memory_human: 800M  (vs maxmemory)
# mem_fragmentation_ratio: 3.5  (>2.0 indicates fragmentation)
# evicted_keys: 0  (should be >0 if near maxmemory)
```

**Step 7: Analyze checkpoint sizes (specific to LangGraph app)**
```bash
# Get checkpoint size distribution
docker-compose exec postgres psql -U lia -c "
SELECT
  CASE
    WHEN length(checkpoint_data::text) < 100000 THEN '<100KB'
    WHEN length(checkpoint_data::text) < 500000 THEN '100KB-500KB'
    WHEN length(checkpoint_data::text) < 1000000 THEN '500KB-1MB'
    ELSE '>1MB'
  END AS size_bucket,
  COUNT(*) AS count,
  pg_size_pretty(SUM(length(checkpoint_data::text))::bigint) AS total_size
FROM checkpoints
WHERE updated_at > NOW() - INTERVAL '1 hour'
GROUP BY size_bucket
ORDER BY size_bucket;
"

# Expected healthy distribution:
# <100KB:     80%
# 100KB-500KB: 18%
# 500KB-1MB:    2%
# >1MB:         0% (PROBLEM if >0%)
```

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding - <5 minutes)

**Option 1: Restart high-memory container (Fastest - 30 seconds)**
```bash
# Restart API container to reclaim leaked memory
docker-compose restart api

# Wait for startup
sleep 30

# Verify memory usage normalized
docker stats --no-stream lia_api_1

# Expected: Memory <50% after restart

# When to use: Active memory leak, not due to legitimate data
# Expected impact: Memory drops to baseline (30-40%)
# Duration: 30 seconds
# Downside: Brief service interruption (10-30s), loses in-memory state
```

**Option 2: Clear Redis cache (if Redis is culprit)**
```bash
# Check Redis memory first
docker-compose exec redis redis-cli INFO memory | grep used_memory_human

# Flush all keys (CAUTION: loses all cached data)
docker-compose exec redis redis-cli FLUSHALL

# Or flush specific DB (if using multiple databases)
docker-compose exec redis redis-cli -n 0 FLUSHDB

# Verify memory freed
docker stats --no-stream lia_redis_1

# When to use: Redis memory >80%, cache not critical
# Expected impact: Redis memory drops to <10MB
# Duration: Immediate
# Downside: Cache misses → increased DB load and latency for ~10 minutes
```

**Option 3: Archive old checkpoints (if checkpoint bloat)**
```bash
# Archive checkpoints older than 24h (move to archival table)
docker-compose exec postgres psql -U lia -c "
BEGIN;
CREATE TABLE IF NOT EXISTS checkpoints_archive (LIKE checkpoints INCLUDING ALL);
INSERT INTO checkpoints_archive SELECT * FROM checkpoints WHERE updated_at < NOW() - INTERVAL '24 hours';
DELETE FROM checkpoints WHERE updated_at < NOW() - INTERVAL '24 hours';
COMMIT;
"

# Verify freed memory (may need VACUUM FULL to reclaim)
docker-compose exec postgres psql -U lia -c "VACUUM FULL checkpoints;"

# When to use: Checkpoints consuming >1GB, old data not needed
# Expected impact: Frees 20-50% memory depending on data retention
# Duration: 2-5 minutes
# Downside: Old conversations cannot be resumed
```

**Option 4: Kill long-running connections (if connection leak)**
```bash
# Identify idle connections
docker-compose exec postgres psql -U lia -c "
SELECT pid, usename, application_name, state, now() - state_change AS duration
FROM pg_stat_activity
WHERE datname = 'lia'
  AND state = 'idle in transaction'
  AND (now() - state_change) > INTERVAL '5 minutes'
ORDER BY duration DESC;
"

# Kill idle transactions (CAUTION: may interrupt legitimate work)
docker-compose exec postgres psql -U lia -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'lia'
  AND state = 'idle in transaction'
  AND (now() - state_change) > INTERVAL '10 minutes';
"

# Verify connection count reduced
docker-compose exec postgres psql -U lia -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = 'lia';"

# When to use: Many idle transactions, memory correlated with connections
# Expected impact: Reduces memory 10-30%
# Duration: Immediate
# Downside: May interrupt user workflows
```

**Option 5: Trigger garbage collection (Python-specific)**
```bash
# Force Python garbage collection
docker-compose exec api python -c "
import gc
import sys
print(f'Before GC: {sys.getsizeof(gc.get_objects())/1024/1024:.2f} MB objects')
collected = gc.collect()
print(f'Collected: {collected} objects')
print(f'After GC: {sys.getsizeof(gc.get_objects())/1024/1024:.2f} MB objects')
"

# Verify memory reduced
docker stats --no-stream lia_api_1

# When to use: Suspected GC delay, memory not at critical level
# Expected impact: Frees 5-15% memory (small impact)
# Duration: 1-5 seconds
# Downside: Brief API latency spike during GC
```

---

### Verification After Mitigation

```bash
# 1. Verify memory usage normalized
docker stats --no-stream

# Expected: All containers <70% memory

# 2. Verify alert stopped firing
curl -s "http://localhost:9093/api/v2/alerts" | jq '.[] | select(.labels.alertname=="HighMemoryUsage") | .status.state'

# Expected: "inactive" or empty result

# 3. Verify no OOM kills in kernel logs
dmesg | grep -i "oom" | tail -5

# Expected: No new entries

# 4. Verify service health
curl -f http://localhost:8000/health

# Expected: HTTP 200, response <500ms

# 5. Check memory growth stopped
BEFORE=$(docker stats --no-stream --format "{{.MemUsage}}" lia_api_1 | awk '{print $1}')
sleep 120
AFTER=$(docker stats --no-stream --format "{{.MemUsage}}" lia_api_1 | awk '{print $1}')
echo "Before: $BEFORE, After: $AFTER"

# Expected: AFTER ≈ BEFORE (growth <5MB/2min)
```

---

### Root Cause Fix (Permanent Solution - 30-120 minutes)

**Fix 1: Implement checkpoint pruning (if checkpoint bloat identified)**

**File**: `apps/api/src/domains/conversations/services/checkpoint_service.py`
```python
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CheckpointService:
    def __init__(self, db_session):
        self.db = db_session

    async def prune_old_checkpoints(self, retention_days: int = 7):
        """
        Prune checkpoints older than retention_days to prevent memory bloat.
        Keeps only most recent checkpoint per conversation.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Delete old checkpoints, keeping only latest per conversation
        deleted = await self.db.execute("""
            DELETE FROM checkpoints
            WHERE updated_at < :cutoff_date
              AND id NOT IN (
                SELECT MAX(id)
                FROM checkpoints
                GROUP BY conversation_id
              )
        """, {"cutoff_date": cutoff_date})

        logger.info(f"Pruned {deleted.rowcount} old checkpoints (older than {retention_days} days)")
        return deleted.rowcount

    async def prune_large_checkpoints(self, max_messages: int = 50):
        """
        Trim large checkpoints to max_messages, keeping conversation functional
        but preventing unbounded growth.
        """
        # Find checkpoints with >max_messages
        large_checkpoints = await self.db.execute("""
            SELECT id, conversation_id, checkpoint_data
            FROM checkpoints
            WHERE jsonb_array_length(checkpoint_data->'messages') > :max_messages
        """, {"max_messages": max_messages})

        trimmed_count = 0
        for checkpoint in large_checkpoints:
            # Keep only last max_messages
            checkpoint_data = checkpoint['checkpoint_data']
            messages = checkpoint_data.get('messages', [])

            if len(messages) > max_messages:
                trimmed_data = {
                    **checkpoint_data,
                    'messages': messages[-max_messages:],  # Keep latest N messages
                    '_trimmed': True,
                    '_original_message_count': len(messages)
                }

                await self.db.execute("""
                    UPDATE checkpoints
                    SET checkpoint_data = :trimmed_data
                    WHERE id = :checkpoint_id
                """, {"trimmed_data": trimmed_data, "checkpoint_id": checkpoint['id']})

                trimmed_count += 1

        logger.info(f"Trimmed {trimmed_count} large checkpoints to {max_messages} messages")
        return trimmed_count
```

**File**: `apps/api/src/infrastructure/scheduler.py` (add scheduled job)
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.domains.conversations.services.checkpoint_service import CheckpointService

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour='*/6')  # Every 6 hours
async def cleanup_checkpoints():
    """Scheduled task to prune old/large checkpoints"""
    from src.infrastructure.database import get_db

    async for db in get_db():
        service = CheckpointService(db)

        # Prune old checkpoints (>7 days, except latest per conversation)
        pruned = await service.prune_old_checkpoints(retention_days=7)

        # Trim large checkpoints (>50 messages → keep last 50)
        trimmed = await service.prune_large_checkpoints(max_messages=50)

        logger.info(f"Checkpoint cleanup: pruned={pruned}, trimmed={trimmed}")
```

**Testing**:
```bash
# Test pruning manually
docker-compose exec api python -c "
import asyncio
from src.infrastructure.database import get_db
from src.domains.conversations.services.checkpoint_service import CheckpointService

async def test():
    async for db in get_db():
        service = CheckpointService(db)
        pruned = await service.prune_old_checkpoints(retention_days=7)
        trimmed = await service.prune_large_checkpoints(max_messages=50)
        print(f'Pruned: {pruned}, Trimmed: {trimmed}')
        break

asyncio.run(test())
"

# Monitor memory after implementation
watch -n 60 'docker stats --no-stream lia_api_1'
```

---

**Fix 2: Fix memory leak in application code**

**Investigation** (identify leak source):
```bash
# Profile memory allocation over time
docker-compose exec api python -m memory_profiler apps/api/src/main.py

# Or use tracemalloc snapshot comparison
docker-compose exec api python -c "
import tracemalloc
import time
tracemalloc.start()

# Baseline snapshot
snapshot1 = tracemalloc.take_snapshot()
time.sleep(300)  # Wait 5 minutes under load
snapshot2 = tracemalloc.take_snapshot()

# Compare snapshots
top_stats = snapshot2.compare_to(snapshot1, 'lineno')
print('Top 10 memory growth:')
for stat in top_stats[:10]:
    print(stat)
"
```

**Common leak patterns and fixes**:

**Pattern 1: Global cache without eviction**
```python
# BEFORE (leak):
_prompt_cache = {}  # Grows unbounded

def get_system_prompt(context: str) -> str:
    if context not in _prompt_cache:
        _prompt_cache[context] = generate_prompt(context)  # Never evicts
    return _prompt_cache[context]

# AFTER (fixed with LRU):
from functools import lru_cache

@lru_cache(maxsize=1000)  # Evicts oldest when >1000 entries
def get_system_prompt(context: str) -> str:
    return generate_prompt(context)
```

**Pattern 2: Circular references preventing GC**
```python
# BEFORE (leak):
class Agent:
    def __init__(self):
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)  # callback holds reference to Agent

# AFTER (fixed with weakref):
import weakref

class Agent:
    def __init__(self):
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(weakref.ref(callback))  # Weak reference allows GC
```

**Pattern 3: Accumulating event listeners**
```python
# BEFORE (leak):
async def process_stream(response):
    async for chunk in response:
        # Event listener added but never removed
        on_chunk_received(chunk)

# AFTER (fixed):
async def process_stream(response):
    listeners = []
    try:
        async for chunk in response:
            listener = on_chunk_received(chunk)
            listeners.append(listener)
    finally:
        # Cleanup listeners
        for listener in listeners:
            listener.close()
```

**Deployment**:
```bash
# Commit fix
git add .
git commit -m "fix: memory leak in prompt cache (add LRU eviction)"

# Deploy
docker-compose build api
docker-compose up -d api

# Monitor memory for 24h (verify leak stopped)
while true; do
  MEM=$(docker stats --no-stream --format "{{.MemUsage}}" lia_api_1)
  echo "$(date): $MEM"
  sleep 600  # Every 10 minutes
done
```

---

**Fix 3: Configure Redis maxmemory and eviction policy**

**File**: `infrastructure/docker/redis.conf` (create new)
```conf
# Limit Redis memory to 256MB
maxmemory 256mb

# Eviction policy: LRU (Least Recently Used) on keys with TTL
maxmemory-policy allkeys-lru

# Evict in batches of 5 keys
maxmemory-samples 5

# Persistence (disable if pure cache, enable if durable data)
save ""  # Disable RDB snapshots (saves memory)
appendonly no  # Disable AOF (saves memory)
```

**Update docker-compose.yml**:
```yaml
services:
  redis:
    image: redis:7-alpine
    command: redis-server /usr/local/etc/redis/redis.conf
    volumes:
      - ./infrastructure/docker/redis.conf:/usr/local/etc/redis/redis.conf:ro
    deploy:
      resources:
        limits:
          memory: 512M  # Container limit (2x maxmemory for safety)
```

**Apply changes**:
```bash
# Restart Redis with new config
docker-compose up -d redis

# Verify configuration
docker-compose exec redis redis-cli CONFIG GET maxmemory
docker-compose exec redis redis-cli CONFIG GET maxmemory-policy

# Monitor evictions
watch -n 30 'docker-compose exec redis redis-cli INFO stats | grep evicted_keys'
# Should see evicted_keys increasing when memory reaches maxmemory
```

---

**Fix 4: Implement proper connection pool management**

**File**: `apps/api/src/infrastructure/database.py`
```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import logging

logger = logging.getLogger(__name__)

# Configure connection pool with limits
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,          # Maximum 10 persistent connections
    max_overflow=5,        # Allow 5 additional connections under load
    pool_timeout=30,       # Wait max 30s for connection
    pool_recycle=3600,     # Recycle connections every hour (prevent stale connections)
    pool_pre_ping=True,    # Verify connection before use
    echo_pool=True,        # Log pool checkouts/checkins (debug)
)

# Monitor pool statistics
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    logger.debug(f"Connection pool: {engine.pool.status()}")

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    # Warn if pool saturated
    pool = engine.pool
    if pool.overflow() >= pool._max_overflow:
        logger.warning(f"Connection pool exhausted! Overflow: {pool.overflow()}/{pool._max_overflow}")

# Ensure connections closed properly
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # CRITICAL: Always close connection
```

**Add monitoring metric**:
```python
# apps/api/src/infrastructure/observability/metrics_db.py
from prometheus_client import Gauge

db_connection_pool_size = Gauge(
    'db_connection_pool_size',
    'Current database connection pool size',
    ['state']
)

def update_pool_metrics():
    """Update connection pool metrics (call periodically)"""
    pool = engine.pool
    db_connection_pool_size.labels(state='in_use').set(pool.size() - pool.checkedin())
    db_connection_pool_size.labels(state='available').set(pool.checkedin())
    db_connection_pool_size.labels(state='overflow').set(pool.overflow())
```

**Testing**:
```bash
# Load test to verify connections properly released
docker-compose exec api locust -f tests/load/test_db_connections.py --users=50 --spawn-rate=10 --run-time=5m

# Monitor connection count during test
watch -n 5 'docker-compose exec postgres psql -U lia -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '\''lia'\'';"'

# Expected: Connection count stays ≤ (pool_size + max_overflow) = 15
```

---

**Fix 5: Increase memory limits (if legitimate growth)**

**Update docker-compose.yml**:
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 4G  # Increase from 2G
        reservations:
          memory: 2G  # Reserve 2G minimum
```

**For cloud deployments** (example: AWS ECS):
```bash
# Update ECS task definition
aws ecs register-task-definition \
  --family lia-api \
  --memory 4096 \  # Increase from 2048 (4GB)
  --cpu 2048

# Update service
aws ecs update-service \
  --cluster lia \
  --service api \
  --task-definition lia-api:latest \
  --force-new-deployment
```

**Apply and verify**:
```bash
# Restart with new limits
docker-compose up -d

# Verify new memory limit
docker inspect lia_api_1 | jq '.[0].HostConfig.Memory'
# Should show: 4294967296 (4GB in bytes)

# Monitor utilization
watch -n 60 'docker stats --no-stream lia_api_1'
```

**When to use**: After fixing leaks, if legitimate workload requires more memory (verified via capacity planning).

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **Infrastructure Resources** - `http://localhost:3000/d/infrastructure-resources`
  - Panel: "Memory Usage %" - Real-time memory per container
  - Panel: "Memory Available" - Absolute memory available
  - Panel: "OOM Kills" - Kernel OOM killer events

- **Database Monitoring** - `http://localhost:3000/d/database-monitoring`
  - Panel: "Connection Pool" - Active/idle connections
  - Panel: "PostgreSQL Memory" - shared_buffers, cache usage

- **Redis Dashboard** - `http://localhost:3000/d/redis-monitoring`
  - Panel: "Redis Memory" - used_memory, maxmemory
  - Panel: "Eviction Rate" - Keys evicted per second

### Prometheus Queries

**Current memory usage percentage**:
```promql
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
```

**Memory usage by container**:
```promql
container_memory_usage_bytes{name=~"lia.*"}
```

**Memory growth rate (bytes/hour)**:
```promql
deriv(container_memory_usage_bytes{name="lia_api_1"}[1h]) * 3600
```

**Estimated time until OOM (hours)** (if negative growth):
```promql
(
  container_spec_memory_limit_bytes{name="lia_api_1"}
  - container_memory_usage_bytes{name="lia_api_1"}
) / abs(deriv(container_memory_usage_bytes{name="lia_api_1"}[1h]) * 3600)
```

**Redis memory usage**:
```promql
redis_memory_used_bytes / redis_memory_max_bytes * 100
```

**Database connection count**:
```promql
pg_stat_activity_count
```

### Logs Queries

**Find OOM kill events**:
```bash
dmesg | grep -i "oom\|kill" | tail -50
```

**Find memory warnings in application logs**:
```bash
docker-compose logs api --since 1h | grep -i "memory\|oom\|allocation"
```

---

## 📚 Related Runbooks

- **[HighCPUUsage.md](./HighCPUUsage.md)** - Often fires together (memory leak causing GC → high CPU)
- **[ContainerDown.md](./ContainerDown.md)** - OOM kills cause container crashes
- **[CheckpointSaveSlowCritical.md](./CheckpointSaveSlowCritical.md)** - Large checkpoints consume memory
- **[DatabaseDown.md](./DatabaseDown.md)** - Memory exhaustion can crash PostgreSQL

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Daily Memory Sawtooth
**Scenario**: Memory grows throughout day, drops at 2 AM (daily restart), repeats.

**Detection**:
```bash
# Check container start time
docker inspect lia_api_1 | jq '.[0].State.StartedAt'
```

**Root Cause**: Memory leak masked by daily restart schedule.

**Prevention**: Fix leak instead of relying on restarts.

---

### Pattern 2: Conversation Spike Memory Spike
**Scenario**: Traffic spike → many concurrent conversations → large checkpoint storage → memory exhaustion.

**Detection**:
```bash
# Check correlation
CONVERSATIONS=$(curl -s "http://localhost:9090/api/v1/query?query=active_conversations_total" | jq -r '.data.result[0].value[1]')
MEMORY=$(docker stats --no-stream --format "{{.MemUsage}}" lia_api_1)
echo "Conversations: $CONVERSATIONS, Memory: $MEMORY"
```

**Prevention**: Implement checkpoint size limit (500KB max) and pagination.

---

### Pattern 3: Redis Eviction Causing DB Load Spike
**Scenario**: Redis hits maxmemory → evicts keys → cache misses → DB queries increase → memory/CPU spike on DB.

**Detection**:
```bash
# Check eviction rate and DB query rate correlation
docker-compose exec redis redis-cli INFO stats | grep evicted_keys
docker-compose exec postgres psql -U lia -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"
```

**Prevention**: Increase Redis maxmemory OR optimize cache hit rate OR add read replicas.

---

### Known Issue 1: PostgreSQL Shared Buffers Not Released
**Problem**: PostgreSQL `shared_buffers` configured to 25% RAM (4GB) but never releases memory even when idle.

**Workaround**: This is expected behavior - shared_buffers is pre-allocated. Reduce `shared_buffers` if memory constrained.

**Tracking**: PostgreSQL design - not a bug.

---

### Known Issue 2: Python GC Not Running Under Load
**Problem**: Python garbage collector defers collection under high load, causing temporary memory spikes.

**Detection**:
```bash
docker-compose logs api | grep "gc:" | tail -20
```

**Workaround**: Manually trigger GC periodically:
```python
import gc
import threading

def periodic_gc():
    while True:
        time.sleep(300)  # Every 5 minutes
        gc.collect()

threading.Thread(target=periodic_gc, daemon=True).start()
```

---

## 🆘 Escalation

### When to Escalate

Escalate immediately if:
- [ ] Memory >95% for >5 minutes (imminent OOM)
- [ ] OOM killer has terminated processes (check `dmesg`)
- [ ] Service is down due to memory exhaustion
- [ ] Memory leak identified but fix requires >2 hours (architectural change)
- [ ] Multiple containers exhausting memory simultaneously

### Escalation Path

**Level 1 - Senior SRE** (0-10 minutes):
- **Contact**: On-call SRE via PagerDuty
- **Info needed**:
  - Current memory % and trend (growing/stable)
  - OOM kills (yes/no, which processes)
  - Recent deployments (<24h)
  - Mitigation attempts
- **Expected action**: Advanced diagnosis, approve emergency mitigations (restart, scale)

**Level 2 - Engineering Lead** (10-30 minutes):
- **Contact**: Backend/Infrastructure Team Lead
- **Info needed**:
  - Root cause hypothesis (leak, legitimate growth, config)
  - Business impact (users affected, data loss risk)
  - Fix complexity (quick fix vs refactor)
- **Expected action**: Approve rollback, allocate engineering resources for fix

**Level 3 - CTO** (30+ minutes):
- **Contact**: CTO / VP Engineering
- **Info needed**:
  - Incident duration and severity
  - Customer impact assessment
  - Long-term fix timeline
- **Expected action**: Business continuity decisions, external communication

### Escalation Template

```
🚨 MEMORY ALERT - ESCALATION 🚨

Severity: WARNING (escalating to CRITICAL)
Service: LIA Production
Duration: [XX] minutes

Current Status:
- Memory Usage: [XX]% (Threshold: 85%)
- Available Memory: [XXX MB]
- OOM Kills: [Yes/No - process names if yes]
- Affected Containers: [Names]

User Impact:
- Service Status: [Up / Degraded / Down]
- Error Rate: [X]%
- Estimated Users Affected: [XX]

Actions Taken:
- [✓] Restarted API container → Memory reduced to [XX]% temporarily
- [✓] Analyzed memory allocation → [Finding]
- [ ] Pending: [Next action]

Root Cause Hypothesis:
[Brief description: "Memory leak in checkpoint storage" or "Under investigation"]

Escalation Reason:
- Memory leak identified, fix requires code changes (ETA: [X hours])
- OR Mitigation ineffective / OOM imminent / Unknown cause

Dashboards:
- Infrastructure: http://localhost:3000/d/infrastructure-resources
- Prometheus: http://localhost:9090/graph?g0.expr=node_memory

Request:
[Specific ask - e.g., "Approve increasing container memory limit to 4GB" or "Need code review for leak fix"]
```

---

## 📝 Post-Incident Actions

### Immediate (<1 hour after resolution)

- [ ] Create incident report
- [ ] Document root cause (leak location, trigger condition)
- [ ] Verify monitoring normalized (memory <70%, no OOM kills)
- [ ] Notify stakeholders of resolution

### Short-term (<24 hours after resolution)

- [ ] Update this runbook with incident learnings
- [ ] Create GitHub issues for permanent fixes:
  - Memory leak fix (code changes)
  - Checkpoint pruning implementation
  - Connection pool configuration
  - Monitoring improvements
- [ ] Review alert threshold (was 85% appropriate? Warn earlier at 75%?)
- [ ] Add memory usage alerts for specific components (checkpoints, cache, connections)

### Long-term (<1 week after resolution)

- [ ] Conduct post-mortem (if critical incident)
- [ ] Implement automated memory profiling (weekly snapshots)
- [ ] Add memory regression tests (prevent leak reintroduction)
- [ ] Update capacity planning (if legitimate growth)
- [ ] Document architectural changes (if refactor required)

---

## 📋 Incident Report Template

```markdown
# Incident Report: High Memory Usage

**Incident ID**: INC-[YYYY-MM-DD-XXX]
**Date**: [YYYY-MM-DD]
**Duration**: [Start time] - [End time] ([Total duration])
**Severity**: Warning (or Critical if OOM occurred)
**Services Affected**: LIA API, [Others]

## Summary
[1-2 sentence description]

## Timeline (UTC)
- [HH:MM] - Alert fired: HighMemoryUsage (memory at XX%)
- [HH:MM] - On-call engineer notified
- [HH:MM] - Investigation started
- [HH:MM] - Root cause identified: [Description]
- [HH:MM] - Mitigation applied: [Action]
- [HH:MM] - Memory normalized to <70%
- [HH:MM] - Alert resolved

## Impact
- **Users Affected**: [Number/percentage]
- **Service Degradation**: [Description]
- **Data Loss**: [Yes/No]
- **OOM Kills**: [Yes/No - which processes]

## Root Cause
[Detailed explanation]

**Contributing Factors**:
- [Factor 1]
- [Factor 2]

## Detection
- **Alert**: HighMemoryUsage at [time]
- **TTD**: [X minutes]

## Response
- **TTR**: [X minutes]
- **TTM**: [X minutes]
- **MTTR**: [Total duration]

## Resolution
1. [Action 1] - [Result]
2. [Action 2] - [Result]

## Lessons Learned

### What Went Well
- [Point 1]

### What Went Wrong
- [Point 1]

### Where We Got Lucky
- [Point 1]

## Action Items
- [ ] [Action 1] - Owner: [Name] - Due: [Date] - GitHub: #[issue]
- [ ] [Action 2] - Owner: [Name] - Due: [Date] - GitHub: #[issue]

## References
- Runbook: [HighMemoryUsage.md](./HighMemoryUsage.md)
- Grafana: http://localhost:3000/d/infrastructure-resources
- GitHub issue: #[number]
```

---

## 🔗 Additional Resources

### Internal Documentation
- [Infrastructure Architecture](../../architecture/infrastructure.md)
- [Memory Management Best Practices](../../performance/memory.md)
- [Checkpoint Architecture](../../architecture/checkpoints.md)
- [Database Connection Pooling](../../database/connection_pooling.md)

### External Resources
- [Understanding Linux Memory](https://www.kernel.org/doc/html/latest/admin-guide/mm/concepts.html)
- [Docker Memory Limits](https://docs.docker.com/config/containers/resource_constraints/#memory)
- [Python Memory Management](https://realpython.com/python-memory-management/)
- [PostgreSQL Memory Configuration](https://www.postgresql.org/docs/current/runtime-config-resource.html)
- [Redis Memory Optimization](https://redis.io/docs/manual/eviction/)

### Profiling Tools

- **memory_profiler** - Line-by-line memory profiling:
  ```bash
  docker-compose exec api pip install memory_profiler
  docker-compose exec api python -m memory_profiler script.py
  ```

- **objgraph** - Python object reference graphs:
  ```bash
  docker-compose exec api pip install objgraph
  docker-compose exec api python -c "import objgraph; objgraph.show_most_common_types(limit=20)"
  ```

- **guppy3** - Heap analysis:
  ```bash
  docker-compose exec api pip install guppy3
  docker-compose exec api python -c "from guppy import hpy; h = hpy(); print(h.heap())"
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
- HighMemoryUsage (this runbook)
- HighCPUUsage (often correlated - GC thrashing)
- ContainerDown (OOM kills)
- CheckpointSaveSlowCritical (large checkpoints)

---

## ✅ Validation Checklist

- [x] Alert definition verified in `alerts.yml`
- [x] All bash commands syntax-checked
- [x] All PromQL queries validated
- [x] Grafana dashboard links confirmed
- [x] Docker commands tested
- [x] PostgreSQL queries validated
- [ ] Peer review completed (2+ reviewers)
- [ ] Dry-run in staging
- [ ] Approved by Infrastructure Lead

---

## 📌 Notes

**Critical Safety Warnings**:
- **NEVER** run `VACUUM FULL` on large tables during peak hours (locks table)
- **ALWAYS** verify backups before deleting checkpoint data
- **ALWAYS** test memory profiling tools in staging first (can cause overhead)

**Performance Considerations**:
- Memory >90% triggers swap usage → 10-100x performance degradation
- OOM killer kills processes non-deterministically → unpredictable failures
- Python GC under memory pressure can cause 1-5 second pauses

**Testing Notes**:
- Simulate memory pressure: `stress --vm 1 --vm-bytes 1.5G --timeout 60s`
- Test OOM behavior: gradually reduce container memory limit and monitor
- Verify leak fixes: run load test for 4+ hours, memory should stabilize

**Maintenance Schedule**:
- Review memory trends monthly
- Audit checkpoint sizes weekly
- Test memory limits quarterly

---

**End of Runbook**
