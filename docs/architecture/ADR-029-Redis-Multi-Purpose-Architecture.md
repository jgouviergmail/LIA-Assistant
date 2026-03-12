# ADR-029: Redis Multi-Purpose Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Centralized Redis for sessions, cache, rate limiting, locks
**Related Documentation**: `docs/technical/REDIS.md`

---

## Context and Problem Statement

L'application nécessitait Redis pour plusieurs use cases :

1. **Session Storage** : BFF pattern avec cookies HTTP-only
2. **OAuth State** : Tokens single-use avec TTL court
3. **Rate Limiting** : Protection API distribuée
4. **Distributed Locks** : Prévention race conditions OAuth refresh
5. **Application Cache** : Réduction latence et coûts LLM

**Question** : Comment architecturer Redis pour ces usages multiples avec isolation ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Database Isolation** : Separate DBs for sessions vs cache
2. **Atomic Operations** : Lua scripts for rate limiting
3. **Auto-Expiration** : TTL-based cleanup
4. **Fail-Open** : Availability over strict limiting

### Nice-to-Have:

- Connection pooling
- Metrics per operation type
- Pattern-based invalidation

---

## Decision Outcome

**Chosen option**: "**Multi-DB Redis + Lua Scripts + Singleton Connections**"

### Architecture Overview

```mermaid
graph TB
    subgraph "REDIS DATABASES"
        DB1[(DB 1<br/>Sessions)]
        DB2[(DB 2<br/>Cache)]
    end

    subgraph "SESSION STORAGE"
        SESS[SessionStore] --> DB1
        SESS --> SS1[session:{id}]
        SESS --> SS2[user:{id}:sessions]
    end

    subgraph "OAUTH STATE"
        OAUTH[SessionService] --> DB1
        OAUTH --> OS1[oauth:state:{token}]
    end

    subgraph "RATE LIMITING"
        RL[RedisRateLimiter] --> DB2
        RL --> LUA[Lua Script<br/>Sliding Window]
        RL --> RK[rate_limit:{key}]
    end

    subgraph "DISTRIBUTED LOCKS"
        LOCK[OAuthLock] --> DB2
        LOCK --> SETNX[SETNX Pattern]
        LOCK --> LK[oauth_lock:{user}:{type}]
    end

    subgraph "APPLICATION CACHE"
        CACHE[cache_set_json] --> DB2
        CACHE --> CK1[contacts_list:{user}]
        CACHE --> CK2[llm_cache:{hash}]
    end

    style DB1 fill:#4CAF50,stroke:#2E7D32,color:#fff
    style DB2 fill:#2196F3,stroke:#1565C0,color:#fff
    style LUA fill:#FF9800,stroke:#F57C00,color:#fff
```

### Connection Management

```python
# apps/api/src/infrastructure/cache/redis.py

# Global singletons for connection reuse
_redis_cache: aioredis.Redis | None = None
_redis_session: aioredis.Redis | None = None

async def get_redis_cache() -> aioredis.Redis:
    """Get Redis client for caching (DB 2)."""
    global _redis_cache
    if _redis_cache is None:
        redis_url = str(settings.redis_url)
        base_url = redis_url.rsplit("/", 1)[0]
        cache_url = f"{base_url}/{settings.redis_cache_db}"
        _redis_cache = aioredis.from_url(
            cache_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_cache

async def get_redis_session() -> aioredis.Redis:
    """Get Redis client for session management (DB 1)."""
    global _redis_session
    if _redis_session is None:
        redis_url = str(settings.redis_url)
        base_url = redis_url.rsplit("/", 1)[0]
        session_url = f"{base_url}/{settings.redis_session_db}"
        _redis_session = aioredis.from_url(
            session_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_session

async def close_redis() -> None:
    """Graceful shutdown of Redis connections."""
    global _redis_cache, _redis_session
    if _redis_cache:
        await _redis_cache.close()
        _redis_cache = None
    if _redis_session:
        await _redis_session.close()
        _redis_session = None
```

### Session Storage (BFF Pattern)

```python
# apps/api/src/infrastructure/cache/session_store.py

class UserSession:
    """Minimal session data (GDPR-compliant) - NO PII stored."""
    def __init__(self, session_id: str, user_id: str, remember_me: bool = False):
        self.session_id = session_id
        self.user_id = user_id  # Only user reference
        self.remember_me = remember_me
        self.created_at = datetime.now(UTC)

class SessionStore:
    async def create_session(self, user_id: str, remember_me: bool = False) -> UserSession:
        session_id = str(uuid4())
        session = UserSession(session_id, user_id, remember_me)

        # Calculate TTL based on remember_me
        ttl = (settings.session_cookie_max_age_remember if remember_me
               else settings.session_cookie_max_age)

        # Store session: session:{id} → JSON
        key = f"session:{session_id}"
        await self.redis.setex(key, ttl, json.dumps(session.to_dict()))

        # Create user index for O(1) bulk deletion
        user_sessions_key = f"user:{user_id}:sessions"
        await self.redis.sadd(user_sessions_key, session_id)
        await self.redis.expire(user_sessions_key, settings.session_cookie_max_age_remember)

        return session

    async def delete_all_user_sessions(self, user_id: str) -> int:
        """Logout from all devices - O(1) lookup via index."""
        user_sessions_key = f"user:{user_id}:sessions"
        session_ids = await self.redis.smembers(user_sessions_key)

        # Atomic batch deletion via pipeline
        pipeline = self.redis.pipeline()
        for session_id in session_ids:
            pipeline.delete(f"session:{session_id}")
        pipeline.delete(user_sessions_key)

        results = await pipeline.execute()
        return sum(1 for result in results[:-1] if result > 0)
```

### OAuth State Storage (Single-Use)

```python
# apps/api/src/infrastructure/cache/redis.py

class SessionService:
    async def store_oauth_state(self, state: str, data: dict, expire_minutes: int = 5) -> None:
        """Store OAuth state token with short TTL."""
        key = f"{REDIS_KEY_OAUTH_STATE_PREFIX}{state}"
        await self.redis.setex(key, expire_minutes * 60, json.dumps(data))

    async def get_oauth_state(self, state: str) -> dict[str, str] | None:
        """
        Retrieve OAuth state (single-use pattern).

        Auto-deletes after retrieval to prevent replay attacks.
        """
        key = f"{REDIS_KEY_OAUTH_STATE_PREFIX}{state}"
        data = await self.redis.get(key)
        if data:
            await self.redis.delete(key)  # Single-use - delete immediately
            return json.loads(data)
        return None
```

### Rate Limiting (Sliding Window + Lua)

```python
# apps/api/src/infrastructure/rate_limiting/redis_limiter.py

# Atomic Lua script for sliding window rate limiting
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local max_calls = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local current_time = tonumber(ARGV[3])
local request_id = ARGV[4]

-- Remove old entries outside the window
redis.call('ZREMRANGEBYSCORE', key, '-inf', current_time - window_seconds)

-- Count current requests in window
local current_count = redis.call('ZCARD', key)

-- Allow if under limit
if current_count < max_calls then
    redis.call('ZADD', key, current_time, request_id)
    redis.call('EXPIRE', key, window_seconds + 10)
    return 1  -- Allowed
else
    return 0  -- Denied
end
"""

class RedisRateLimiter:
    async def acquire(self, key: str, max_calls: int, window_seconds: int) -> bool:
        """
        Attempt to acquire rate limit token.

        Uses ZSET (Sorted Set) with timestamp scores for sliding window.
        """
        script_sha = await self._ensure_script_loaded()
        current_time = time.time()
        request_id = f"{current_time:.6f}"

        result = await self.redis.evalsha(
            script_sha,
            1,  # Number of keys
            key,
            str(max_calls),
            str(window_seconds),
            str(current_time),
            request_id,
        )

        allowed = bool(result)

        # Record metrics
        if allowed:
            redis_rate_limit_allows_total.labels(key_prefix=extract_key_prefix(key)).inc()
        else:
            redis_rate_limit_hits_total.labels(key_prefix=extract_key_prefix(key)).inc()

        return allowed
```

### Distributed Locks (SETNX Pattern)

```python
# apps/api/src/infrastructure/locks/oauth_lock.py

class OAuthLock:
    """
    Distributed lock using Redis SETNX pattern.

    Prevents race conditions during OAuth token refresh.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        user_id: UUID,
        connector_type: ConnectorType,
        timeout_seconds: int = 10,
    ):
        self.redis = redis_client
        self.lock_key = f"oauth_lock:{user_id}:{connector_type.value}"
        self.timeout_seconds = timeout_seconds

    async def __aenter__(self) -> "OAuthLock":
        """Acquire lock with exponential backoff retry."""
        while True:
            acquired = await self.redis.set(
                self.lock_key,
                "locked",
                nx=True,  # Only set if NOT exists
                ex=self.timeout_seconds,  # Auto-expire
            )

            if acquired:
                self.lock_acquired = True
                return self

            # Exponential backoff
            await asyncio.sleep(wait_time)

    async def __aexit__(self, *args) -> None:
        """Release lock on context exit."""
        if self.lock_acquired:
            await self.redis.delete(self.lock_key)
```

### Cache Helpers

```python
# apps/api/src/infrastructure/cache/redis_helpers.py

async def cache_set_json(
    redis_client: aioredis.Redis,
    key: str,
    value: dict | list,
    ttl_seconds: int,
    add_timestamp: bool = True,
) -> None:
    """Set JSON data with automatic serialization and timestamp."""
    cache_data = {"data": value}
    if add_timestamp:
        cache_data["cached_at"] = datetime.now(UTC).isoformat()

    json_str = json.dumps(cache_data, ensure_ascii=False)
    await redis_client.setex(key, ttl_seconds, json_str)

async def cache_get_or_compute(
    redis_client: aioredis.Redis,
    key: str,
    ttl_seconds: int,
    compute_fn: Callable[[], Awaitable[dict]],
    force_refresh: bool = False,
) -> dict:
    """Cache-aside pattern: Get from cache or compute and cache."""
    if not force_refresh:
        cache_data = await cache_get_json(redis_client, key)
        if cache_data:
            return {**cache_data, "from_cache": True}

    computed_data = await compute_fn()
    await cache_set_json(redis_client, key, computed_data, ttl_seconds)
    return {"data": computed_data, "from_cache": False}

async def cache_invalidate_pattern(redis_client: aioredis.Redis, pattern: str) -> int:
    """Invalidate keys matching pattern using SCAN (not KEYS)."""
    deleted_count = 0
    cursor = 0

    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            deleted_count += await redis_client.delete(*keys)
        if cursor == 0:
            break

    return deleted_count
```

### Key Naming Conventions

| Pattern | Example | TTL | Purpose |
|---------|---------|-----|---------|
| `session:{id}` | `session:abc123` | 7-30 days | User session |
| `user:{id}:sessions` | `user:uuid:sessions` | 30 days | Session index |
| `oauth:state:{token}` | `oauth:state:xyz` | 5 min | OAuth CSRF |
| `oauth_lock:{user}:{type}` | `oauth_lock:uuid:GOOGLE_GMAIL` | 10 sec | Refresh lock |
| `contacts_list:{user}` | `contacts_list:uuid` | 5 min | Contacts cache |
| `contacts_search:{user}:{hash}` | `contacts_search:uuid:a1b2c3` | 3 min | Search cache |
| `llm_cache:{func}:{hash}` | `llm_cache:router:sha256` | 5 min | LLM response |

### Cache TTL Configuration

```python
# apps/api/src/core/constants.py

# Session TTLs
SESSION_COOKIE_MAX_AGE = 604800        # 7 days
SESSION_COOKIE_MAX_AGE_REMEMBER = 2592000  # 30 days

# Google API Cache
GOOGLE_CONTACTS_LIST_CACHE_TTL = 300    # 5 minutes
GOOGLE_CONTACTS_SEARCH_CACHE_TTL = 180  # 3 minutes
GOOGLE_CONTACTS_DETAILS_CACHE_TTL = 600 # 10 minutes

# Email Cache (more volatile)
EMAILS_CACHE_LIST_TTL_SECONDS = 60      # 1 minute
EMAILS_CACHE_SEARCH_TTL_SECONDS = 60    # 1 minute
EMAILS_CACHE_DETAILS_TTL_SECONDS = 300  # 5 minutes

# LLM Cache
LLM_CACHE_TTL_SECONDS = 300             # 5 minutes
```

### Metrics & Observability

```python
# apps/api/src/infrastructure/observability/metrics_redis.py

redis_rate_limit_allows_total = Counter(
    "redis_rate_limit_allows_total",
    "Total rate limit allows",
    ["key_prefix"],
)

redis_rate_limit_hits_total = Counter(
    "redis_rate_limit_hits_total",
    "Total rate limit hits (rejected)",
    ["key_prefix"],
)

redis_rate_limit_check_duration_seconds = Histogram(
    "redis_rate_limit_check_duration_seconds",
    "Duration of rate limit check",
    ["key_prefix"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

def extract_key_prefix(key: str) -> str:
    """Convert high-cardinality keys to low-cardinality prefixes."""
    parts = key.split(":")
    prefix_parts = [p for p in parts if not p.isdigit()]
    return "_".join(prefix_parts)
```

### Application Initialization

```python
# apps/api/src/main.py

from src.infrastructure.cache.redis import close_redis, get_redis_cache

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await get_redis_cache()  # Initialize connections
    yield
    # Shutdown
    await close_redis()  # Graceful cleanup
```

### Consequences

**Positive**:
- ✅ **DB Isolation** : Sessions (DB 1) vs Cache (DB 2)
- ✅ **Atomic Rate Limiting** : Lua scripts prevent race conditions
- ✅ **Auto-Expiration** : TTL-based cleanup, no manual GC
- ✅ **Fail-Open** : Availability prioritized
- ✅ **Single-Use Tokens** : OAuth replay protection

**Negative**:
- ⚠️ Redis single point of failure (needs HA/Sentinel)
- ⚠️ Lua script debugging complexity

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Separate Redis DBs (sessions vs cache)
- [x] ✅ Singleton connection pattern
- [x] ✅ Session storage with user index
- [x] ✅ Single-use OAuth state tokens
- [x] ✅ Sliding window rate limiting (Lua)
- [x] ✅ SETNX distributed locks
- [x] ✅ Cache helpers with TTL
- [x] ✅ Prometheus metrics integration

---

## References

### Source Code
- **Redis Connections**: `apps/api/src/infrastructure/cache/redis.py`
- **Session Store**: `apps/api/src/infrastructure/cache/session_store.py`
- **Redis Helpers**: `apps/api/src/infrastructure/cache/redis_helpers.py`
- **Rate Limiter**: `apps/api/src/infrastructure/rate_limiting/redis_limiter.py`
- **OAuth Lock**: `apps/api/src/infrastructure/locks/oauth_lock.py`
- **Redis Metrics**: `apps/api/src/infrastructure/observability/metrics_redis.py`

### Runbooks
- `docs/runbooks/redis/RedisRateLimitErrors.md`
- `docs/runbooks/redis/RedisConnectionPoolExhaustion.md`

---

**Fin de ADR-029** - Redis Multi-Purpose Architecture Decision Record.
