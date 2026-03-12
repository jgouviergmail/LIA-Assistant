# ADR-017: Rate Limiting Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Sprint 16 - Gold-Grade Resilience
**Related Documentation**: `docs/technical/RATE_LIMITING.md`

---

## Context and Problem Statement

L'application devait gérer deux niveaux de rate limiting :

1. **Tool-level** : Limiter les appels par utilisateur (protection abus)
2. **API Client-level** : Respecter les quotas des APIs externes (Google, OpenWeatherMap)

**Problèmes** :
- Single-instance rate limiting insuffisant (scaling horizontal)
- Pas de fallback si Redis indisponible
- Incohérence entre tools (certains limités, d'autres non)

**Question** : Comment implémenter un rate limiting distribué, résilient et uniforme ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Distribué** : Fonctionne en cluster (multiple instances)
2. **Résilient** : Fallback local si Redis down
3. **Per-user** : Isolation utilisateurs
4. **Configurable** : Limites par catégorie (read, write, expensive)

### Nice-to-Have:

- Sliding window (plus précis que fixed window)
- Métriques Prometheus
- Headers X-RateLimit-* pour clients

---

## Decision Outcome

**Chosen option**: "**Redis Sliding Window + Local Fallback**"

### Architecture Overview

```mermaid
graph TB
    subgraph "TOOL EXECUTION"
        T[Tool Call] --> RL[@rate_limit decorator]
    end

    subgraph "RATE LIMITER"
        RL --> CHECK{Redis<br/>Available?}
        CHECK -->|Yes| REDIS[Redis Sliding Window]
        CHECK -->|No| LOCAL[Local Token Bucket]
    end

    subgraph "REDIS (Primary)"
        REDIS --> LUA[Lua Script<br/>Atomic ZADD/ZCOUNT]
        LUA --> KEY[user:{id}:tool:{name}]
    end

    subgraph "LOCAL FALLBACK"
        LOCAL --> MEM[In-Memory Dict]
        MEM --> TB[Token Bucket]
    end

    subgraph "RESPONSE"
        REDIS --> DEC{Allowed?}
        LOCAL --> DEC
        DEC -->|Yes| EXEC[Execute Tool]
        DEC -->|No| ERR[429 Too Many Requests]
    end

    style RL fill:#4CAF50,stroke:#2E7D32,color:#fff
    style REDIS fill:#2196F3,stroke:#1565C0,color:#fff
    style LOCAL fill:#FF9800,stroke:#F57C00,color:#fff
```

### Rate Limit Decorator

```python
# apps/api/src/domains/agents/utils/rate_limiting.py

def rate_limit(
    max_calls: int | Callable[[], int],
    window_seconds: int | Callable[[], int],
    scope: Literal["user", "global"] = "user",
):
    """
    Decorator for rate limiting tool calls.

    Supports:
    - Static limits: max_calls=20
    - Dynamic limits: max_calls=lambda: settings.rate_limit_read_calls
    - Per-user or global scope
    - Redis distributed + local fallback

    Args:
        max_calls: Maximum calls allowed in window
        window_seconds: Time window in seconds
        scope: "user" (per-user isolation) or "global" (shared)

    Usage:
        @tool
        @rate_limit(max_calls=20, window_seconds=60, scope="user")
        async def search_contacts_tool(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user_id from runtime
            runtime = _extract_runtime(args, kwargs)
            user_id = runtime.config.get("configurable", {}).get("user_id", "anonymous")

            # Resolve dynamic limits
            resolved_max = max_calls() if callable(max_calls) else max_calls
            resolved_window = window_seconds() if callable(window_seconds) else window_seconds

            # Build rate limit key
            if scope == "user":
                key = f"ratelimit:user:{user_id}:tool:{func.__name__}"
            else:
                key = f"ratelimit:global:tool:{func.__name__}"

            # Check rate limit
            limiter = get_rate_limiter()
            allowed, remaining, reset_at = await limiter.check(
                key=key,
                max_calls=resolved_max,
                window_seconds=resolved_window,
            )

            if not allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    tool=func.__name__,
                    user_id=user_id,
                    limit=resolved_max,
                    window=resolved_window,
                )
                raise RateLimitExceededError(
                    tool_name=func.__name__,
                    limit=resolved_max,
                    window_seconds=resolved_window,
                    retry_after=reset_at,
                )

            # Execute tool
            return await func(*args, **kwargs)

        return wrapper
    return decorator
```

### Redis Sliding Window Limiter

```python
# apps/api/src/infrastructure/rate_limiting/redis_limiter.py

class RedisSlidingWindowLimiter:
    """
    Distributed rate limiter using Redis sorted sets.

    Uses sliding window algorithm:
    - ZADD: Add timestamp for each request
    - ZREMRANGEBYSCORE: Remove expired entries
    - ZCOUNT: Count requests in window

    Lua script ensures atomicity.
    """

    # Lua script for atomic rate limiting
    LUA_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])

    -- Remove expired entries
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000)

    -- Count current entries
    local count = redis.call('ZCOUNT', key, '-inf', '+inf')

    if count < limit then
        -- Add new entry
        redis.call('ZADD', key, now, now .. ':' .. math.random())
        redis.call('EXPIRE', key, window)
        return {1, limit - count - 1, 0}  -- allowed, remaining, reset_at
    else
        -- Get oldest entry for reset time
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local reset_at = oldest[2] and (oldest[2] + window * 1000 - now) or window * 1000
        return {0, 0, reset_at}  -- not allowed, 0 remaining, reset_at ms
    end
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._script_sha: str | None = None

    async def check(
        self,
        key: str,
        max_calls: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        Check if request is allowed.

        Returns:
            (allowed: bool, remaining: int, reset_at_ms: int)
        """
        try:
            now_ms = int(time.time() * 1000)

            # Load script if not cached
            if self._script_sha is None:
                self._script_sha = await self.redis.script_load(self.LUA_SCRIPT)

            # Execute atomic check
            result = await self.redis.evalsha(
                self._script_sha,
                1,  # number of keys
                key,
                now_ms,
                window_seconds,
                max_calls,
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_at = int(result[2])

            # Metrics
            rate_limit_checks_total.labels(
                tool=key.split(":")[-1],
                result="allowed" if allowed else "denied",
            ).inc()

            return allowed, remaining, reset_at

        except RedisError as e:
            logger.warning(
                "redis_rate_limit_error",
                error=str(e),
                key=key,
            )
            # Fallback to local limiter
            return await self._local_fallback(key, max_calls, window_seconds)

    async def _local_fallback(
        self,
        key: str,
        max_calls: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """Fallback to local token bucket if Redis unavailable."""
        return await LocalTokenBucketLimiter.check(key, max_calls, window_seconds)
```

### Local Token Bucket Fallback

```python
# apps/api/src/infrastructure/rate_limiting/local_limiter.py

class LocalTokenBucketLimiter:
    """
    In-memory token bucket rate limiter.

    Used as fallback when Redis is unavailable.
    Per-instance only (not distributed).
    """

    _buckets: ClassVar[dict[str, TokenBucket]] = {}
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def check(
        cls,
        key: str,
        max_calls: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """Check if request allowed using token bucket."""
        async with cls._lock:
            bucket = cls._buckets.get(key)

            if bucket is None:
                bucket = TokenBucket(
                    capacity=max_calls,
                    refill_rate=max_calls / window_seconds,
                )
                cls._buckets[key] = bucket

            allowed = bucket.consume(1)
            remaining = int(bucket.tokens)
            reset_at = int((max_calls - remaining) / bucket.refill_rate * 1000)

            return allowed, remaining, reset_at


@dataclass
class TokenBucket:
    """Token bucket implementation."""

    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(default=0)
    last_refill: float = field(default_factory=time.time)

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
```

### Configuration (Categories)

```python
# apps/api/src/core/config/connectors.py

class ConnectorsSettings(BaseSettings):
    """Rate limiting configuration."""

    # Tool Rate Limits (per-user)
    rate_limit_default_read_calls: int = Field(
        default=20,
        description="Read operations: search, list, get"
    )
    rate_limit_default_read_window: int = Field(
        default=60,
        description="Window in seconds for read operations"
    )

    rate_limit_default_write_calls: int = Field(
        default=5,
        description="Write operations: create, update, delete, send"
    )
    rate_limit_default_write_window: int = Field(
        default=60,
        description="Window in seconds for write operations"
    )

    rate_limit_default_expensive_calls: int = Field(
        default=2,
        description="Expensive operations: export, bulk"
    )
    rate_limit_default_expensive_window: int = Field(
        default=300,
        description="Window in seconds for expensive operations (5 min)"
    )

    # API Client Rate Limits (respect external quotas)
    client_rate_limit_google_per_second: int = Field(
        default=10,
        description="Google APIs: 10 req/s per user"
    )
    client_rate_limit_openweathermap_per_second: int = Field(
        default=1,
        description="OpenWeatherMap: 1 req/s (free tier)"
    )
```

### Usage in Tools

```python
# apps/api/src/domains/agents/tools/google_contacts_tools.py

@tool
@track_tool_metrics(...)
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_read_calls,  # 20
    window_seconds=lambda: get_settings().rate_limit_default_read_window,  # 60
    scope="user",
)
async def search_contacts_tool(
    query: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Search contacts - READ operation, 20 calls/minute."""
    ...


@tool
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_write_calls,  # 5
    window_seconds=lambda: get_settings().rate_limit_default_write_window,  # 60
    scope="user",
)
async def send_email_tool(
    to: str,
    subject: str,
    body: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Send email - WRITE operation, 5 calls/minute."""
    ...
```

### Consequences

**Positive**:
- ✅ **Distribué** : Redis sliding window fonctionne en cluster
- ✅ **Résilient** : Fallback local si Redis down
- ✅ **Per-user** : Isolation via key `user:{id}:tool:{name}`
- ✅ **Configurable** : 3 catégories (read, write, expensive)
- ✅ **Atomic** : Lua script évite race conditions
- ✅ **Métriques** : Prometheus counters par tool/result

**Negative**:
- ⚠️ Latence Redis (~1ms par check)
- ⚠️ Local fallback non distribué (risque sur-utilisation)

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Redis sliding window avec Lua script
- [x] ✅ Local token bucket fallback
- [x] ✅ Decorator @rate_limit
- [x] ✅ 3 catégories configurables
- [x] ✅ Métriques Prometheus
- [x] ✅ Per-user isolation

---

## Related Decisions

- [ADR-015: ConnectorTool](ADR-015-ConnectorTool-Base-Class-Pattern.md) - Utilise rate limiting
- [ADR-009: Config Split](ADR-009-Config-Module-Split.md) - Configuration dans connectors.py

---

## References

### Source Code
- **Redis Limiter**: `apps/api/src/infrastructure/rate_limiting/redis_limiter.py`
- **Local Limiter**: `apps/api/src/infrastructure/rate_limiting/local_limiter.py`
- **Decorator**: `apps/api/src/domains/agents/utils/rate_limiting.py`
- **Config**: `apps/api/src/core/config/connectors.py`

### External References
- **Redis Rate Limiting**: https://redis.io/docs/manual/patterns/rate-limiting/
- **Sliding Window Algorithm**: https://blog.cloudflare.com/counting-things-a-lot-of-different-things/

---

**Fin de ADR-017** - Rate Limiting Architecture Decision Record.
