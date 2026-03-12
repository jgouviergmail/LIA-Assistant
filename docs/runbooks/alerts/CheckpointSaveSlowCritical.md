# CheckpointSaveSlowCritical - Runbook

**Severity**: Warning
**Component**: Agents
**Impact**: Slow conversation state persistence, potential data loss if crashes occur
**SLA Impact**: Potential - Affects conversation reliability

---

## 1. Alert Definition

**Alert Name**: `CheckpointSaveSlowCritical`

**PromQL Query**:
```promql
histogram_quantile(0.95, rate(checkpoint_save_duration_seconds_bucket[5m])) > <<<ALERT_CHECKPOINT_SAVE_SLOW_CRITICAL_SECONDS>>>
```

**Thresholds**:
- **Production**: P95 >3 seconds (Critical - should be <1s)
- **Staging**: P95 >5 seconds
- **Development**: P95 >10 seconds

**Duration**: For 5 minutes

**Labels**:
```yaml
severity: warning
component: agents
alert_type: performance
impact: data_persistence
```

**Annotations**:
```yaml
summary: "Checkpoint save critically slow: P95={{ $value }}s"
description: "Checkpoint persistence taking {{ $value }}s at P95 (threshold: <<<ALERT_CHECKPOINT_SAVE_SLOW_CRITICAL_SECONDS>>>s)"
```

---

## 2. Symptoms

### What Users See
- Delayed response streaming (waits for checkpoint save)
- "Saving..." indicator taking >3 seconds
- Occasional "Failed to save conversation" errors

### What Ops See
- `checkpoint_save_duration_seconds` P95 >3s
- PostgreSQL `checkpoints` table write latency high
- Database connection pool saturation
- Disk I/O high on database volume

---

## 3. Possible Causes

### Cause 1: Large Checkpoint Size (Serialized State Too Big) (High Likelihood)
**Description**: LangGraph state contains large objects (conversation history, context, embeddings) causing slow serialization and DB writes.

**Likelihood**: High (50%)

**Verification**:
```bash
# Check checkpoint sizes in database
docker-compose exec postgres psql -U lia -c "
SELECT
  conversation_id,
  pg_size_pretty(length(checkpoint_data::text)::bigint) AS checkpoint_size,
  created_at
FROM checkpoints
ORDER BY length(checkpoint_data::text) DESC
LIMIT 10;
"

# Sizes >1MB indicate bloat
# Check average size
docker-compose exec postgres psql -U lia -c "
SELECT
  pg_size_pretty(AVG(length(checkpoint_data::text)::bigint)::bigint) AS avg_size,
  pg_size_pretty(MAX(length(checkpoint_data::text)::bigint)::bigint) AS max_size
FROM checkpoints;
"
```

---

### Cause 2: Database Write Performance Degradation (Medium-High Likelihood)
**Description**: PostgreSQL experiencing slow writes due to disk I/O, missing indexes, or bloat.

**Likelihood**: Medium-High (40%)

**Verification**:
```bash
# Check database write latency
docker-compose exec postgres psql -U lia -c "
SELECT
  schemaname,
  tablename,
  n_tup_ins,
  n_tup_upd,
  n_live_tup,
  n_dead_tup,
  last_autovacuum,
  last_autoanalyze
FROM pg_stat_user_tables
WHERE tablename = 'checkpoints';
"

# Check table bloat
docker-compose exec postgres psql -U lia -c "
SELECT
  pg_size_pretty(pg_total_relation_size('checkpoints')) AS total_size,
  pg_size_pretty(pg_relation_size('checkpoints')) AS table_size,
  pg_size_pretty(pg_indexes_size('checkpoints')) AS indexes_size;
"

# Check disk I/O
docker stats --no-stream lia_postgres_1
```

---

### Cause 3: Synchronous Checkpoint Save Blocking Request (Medium Likelihood)
**Description**: Application waits synchronously for checkpoint save before responding to user.

**Likelihood**: Medium (30%)

**Verification**:
```bash
# Check if checkpoint save is in critical path
grep -n "await.*checkpoint.*save" apps/api/src/domains/agents/ -r

# Check request duration vs checkpoint duration
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket{path=~\"/api/agents.*\"}[5m]))" | jq '.data.result[0].value[1]'
```

---

### Cause 4: Database Connection Pool Exhaustion (Low-Medium Likelihood)
**Description**: All connections busy, checkpoint save waits for available connection.

**Likelihood**: Low-Medium (20%)

**Verification**:
```bash
# Check connection pool metrics
curl -s "http://localhost:9090/api/v1/query?query=sqlalchemy_pool_connections{state=\"busy\"}/sqlalchemy_pool_connections{state=\"total\"}" | jq '.data.result[0].value[1]'

# Check active connections
docker-compose exec postgres psql -U lia -c "
SELECT count(*) FROM pg_stat_activity WHERE datname='lia';
"
```

---

## 4. Resolution Steps

### Immediate Mitigation

**Option 1: Make checkpoint save asynchronous (Fastest - code change)**

**File**: `apps/api/src/domains/agents/graph.py`
```python
import asyncio

async def save_checkpoint_async(state, config):
    # Don't block user response on checkpoint save
    asyncio.create_task(checkpointer.aput(state, config))
    return state

# In graph definition
graph.add_node("response", response_node)
graph.add_node("save_checkpoint", save_checkpoint_async)  # Non-blocking
```

---

**Option 2: Add index on checkpoints table (Medium - 2 minutes)**

```bash
# Create index on frequently queried columns
docker-compose exec postgres psql -U lia -c "
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_checkpoints_conversation_id_created
ON checkpoints(conversation_id, created_at DESC);
"

# Verify index usage
docker-compose exec postgres psql -U lia -c "
EXPLAIN ANALYZE
SELECT * FROM checkpoints
WHERE conversation_id = 'test-123'
ORDER BY created_at DESC
LIMIT 1;
"
```

---

**Option 3: Implement checkpoint pruning (Medium - 5 minutes)**

```bash
# Delete old checkpoints (keep only last 10 per conversation)
docker-compose exec postgres psql -U lia -c "
DELETE FROM checkpoints
WHERE id IN (
  SELECT id FROM (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY created_at DESC) as rn
    FROM checkpoints
  ) t
  WHERE rn > 10
);
"

# Vacuum to reclaim space
docker-compose exec postgres psql -U lia -c "VACUUM ANALYZE checkpoints;"
```

---

### Root Cause Fix

**Fix 1: Reduce checkpoint state size**

**File**: `apps/api/src/domains/agents/utils/state_cleanup.py`
```python
def cleanup_state_for_checkpoint(state: dict) -> dict:
    """Remove large, non-essential data before checkpointing"""
    cleaned = state.copy()

    # Remove large objects
    if "embeddings" in cleaned:
        del cleaned["embeddings"]  # Recompute if needed

    # Truncate conversation history (keep only last N messages)
    if "messages" in cleaned and len(cleaned["messages"]) > 20:
        cleaned["messages"] = cleaned["messages"][-20:]

    # Remove temporary processing data
    cleaned.pop("intermediate_results", None)
    cleaned.pop("debug_info", None)

    return cleaned

# Use before saving
state_to_save = cleanup_state_for_checkpoint(state)
await checkpointer.aput(state_to_save, config)
```

---

**Fix 2: Implement checkpoint compression**

**File**: `apps/api/src/infrastructure/database/checkpointer.py`
```python
import gzip
import json

def compress_checkpoint(data: dict) -> bytes:
    """Compress checkpoint data before DB write"""
    json_str = json.dumps(data)
    compressed = gzip.compress(json_str.encode('utf-8'))
    return compressed

def decompress_checkpoint(compressed: bytes) -> dict:
    """Decompress checkpoint data after DB read"""
    decompressed = gzip.decompress(compressed)
    return json.loads(decompressed.decode('utf-8'))

# Update checkpointer
class CompressedPostgresSaver(PostgresSaver):
    async def aput(self, config, checkpoint):
        compressed = compress_checkpoint(checkpoint)
        # Save compressed data to DB
        await super().aput(config, compressed)
```

---

**Fix 3: Move checkpoints to Redis (if appropriate)**

**File**: `apps/api/src/core/config.py`
```python
# Use Redis for ephemeral checkpoints, PostgreSQL for long-term
CHECKPOINT_BACKEND = "redis"  # "postgres" | "redis" | "hybrid"
CHECKPOINT_TTL_SECONDS = 3600  # 1 hour in Redis
```

**Implementation**:
```python
from redis import asyncio as aioredis

class RedisCheckpointer:
    def __init__(self, redis_url: str, ttl: int = 3600):
        self.redis = aioredis.from_url(redis_url)
        self.ttl = ttl

    async def aput(self, config, checkpoint):
        key = f"checkpoint:{config['conversation_id']}:{config['checkpoint_id']}"
        await self.redis.setex(key, self.ttl, json.dumps(checkpoint))

    async def aget(self, config):
        key = f"checkpoint:{config['conversation_id']}:{config['checkpoint_id']}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None
```

---

**Fix 4: Partition checkpoints table by conversation_id**

```sql
-- Create partitioned table (requires migration)
CREATE TABLE checkpoints_partitioned (
    id SERIAL,
    conversation_id TEXT NOT NULL,
    checkpoint_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
) PARTITION BY HASH (conversation_id);

-- Create 8 partitions
CREATE TABLE checkpoints_part_0 PARTITION OF checkpoints_partitioned
FOR VALUES WITH (MODULUS 8, REMAINDER 0);

-- ... create partitions 1-7

-- Migrate data
INSERT INTO checkpoints_partitioned SELECT * FROM checkpoints;
```

---

## 5. Related Dashboards & Queries

### Prometheus Queries

**Checkpoint save latency P95**:
```promql
histogram_quantile(0.95, rate(checkpoint_save_duration_seconds_bucket[5m]))
```

**Checkpoint size average**:
```promql
avg(checkpoint_size_bytes)
```

**Checkpoint save rate**:
```promql
rate(checkpoint_saves_total[5m])
```

---

## 6. Related Runbooks
- [CriticalDatabaseConnections.md](./CriticalDatabaseConnections.md) - Pool exhaustion
- [CriticalLatencyP99.md](./CriticalLatencyP99.md) - Overall latency impact

---

## 7. Common Patterns

### Pattern 1: Checkpoint Bloat from Debug Data
**Scenario**: Development logging accidentally left in production, state contains gigabytes of debug data.

**Detection**:
```bash
# Check for debug fields in checkpoints
docker-compose exec postgres psql -U lia -c "
SELECT checkpoint_data->'debug_info' FROM checkpoints LIMIT 5;
"
```

**Fix**: Remove debug data collection in production config.

---

## 8. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
