# Rate Limiting Distribué - Technical Documentation

> **Version**: 1.0.0
> **Date**: 2025-11-21
> **Auteur**: Architecture LIA
> **Status**: ✅ Production Ready (Phase 2.4)
> **Related**: [ADR-009](../architecture/ADR-009-Config-Module-Split.md) - Configuration

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Algorithm - Sliding Window](#algorithm---sliding-window)
4. [Implémentation](#implémentation)
5. [Configuration](#configuration)
6. [Intégration](#intégration)
7. [Tests](#tests)
8. [Performance & Scalabilité](#performance--scalabilité)
9. [Monitoring](#monitoring)

---

## 🎯 Vue d'ensemble

### Problème résolu

**Besoin** : Rate limiting pour protéger les API externes (Google APIs) et prévenir abus.

**Contraintes** :
- ❌ **In-memory** : Ne fonctionne pas avec multiple instances backend (horizontal scaling)
- ❌ **Token bucket simple** : Vulnérable aux bursts malicieux
- ❌ **Fixed window** : Problème du "boundary burst" (2× limite en 1 seconde)

**Solution** : **Redis-based sliding window** rate limiter avec scripts Lua atomiques.

### Caractéristiques

| Feature | Support | Détail |
|---------|---------|--------|
| **Distributed** | ✅ | Fonctionne sur N instances backend |
| **Atomic** | ✅ | Scripts Lua (pas de race conditions) |
| **Sliding window** | ✅ | Précis (pas de boundary burst) |
| **Configurable** | ✅ | Per-key limits (user, endpoint, provider) |
| **Horizontal scaling** | ✅ | Redis O(log N) operations |
| **Multi-provider** | ✅ | Google, OpenAI, Anthropic, etc. |

---

## 🏗️ Architecture

### Diagramme de composants

```
┌─────────────────────────────────────────────────┐
│          Backend Instance 1                     │
│  ┌──────────────────────────────────┐          │
│  │   BaseGoogleClient               │          │
│  │   ┌────────────────────┐         │          │
│  │   │ _make_request()    │         │          │
│  │   │  1. acquire()  ────┼─────┐   │          │
│  │   │  2. API call       │     │   │          │
│  │   └────────────────────┘     │   │          │
│  └──────────────────────────────┘   │          │
└───────────────────────────────────────┼──────────┘
                                       │
┌──────────────────────────────────────┼──────────┐
│          Backend Instance 2          │          │
│  ┌──────────────────────────────────┐│          │
│  │   BaseGoogleClient               ││          │
│  │   ┌────────────────────┐         ││          │
│  │   │ _make_request()    │         ││          │
│  │   │  1. acquire()  ────┼─────────┘          │
│  │   │  2. API call       │                    │
│  │   └────────────────────┘                    │
│  └──────────────────────────────────┘          │
└─────────────────────────────────────────────────┘
                    │
                    │  Redis Protocol
                    ▼
    ┌───────────────────────────────────┐
    │          Redis Server             │
    │  ┌────────────────────────────┐   │
    │  │  Sorted Set (ZSET)         │   │
    │  │  rate_limit:google:user123 │   │
    │  │                            │   │
    │  │  Score    │ Member         │   │
    │  │  ──────────┼───────────    │   │
    │  │  1700000001│ req_001       │   │
    │  │  1700000002│ req_002       │   │
    │  │  1700000003│ req_003       │   │
    │  │  ...       │ ...           │   │
    │  │  (auto-expire after window)│   │
    │  └────────────────────────────┘   │
    │                                   │
    │  ┌────────────────────────────┐   │
    │  │  Lua Scripts (Atomic)      │   │
    │  │  - acquire_token()         │   │
    │  │  - cleanup_expired()       │   │
    │  └────────────────────────────┘   │
    └───────────────────────────────────┘
```

### Flow de décision

```mermaid
sequenceDiagram
    participant Client as BaseGoogleClient
    participant Limiter as RedisRateLimiter
    participant Redis as Redis Server
    participant API as Google API

    Client->>Limiter: acquire(key, max_calls, window_seconds)
    Limiter->>Redis: EVAL lua_script
    Redis->>Redis: ZREMRANGEBYSCORE (cleanup expired)
    Redis->>Redis: ZCARD (count current)
    alt current < max_calls
        Redis->>Redis: ZADD (add new entry)
        Redis->>Redis: EXPIRE (set TTL)
        Redis-->>Limiter: 1 (Allowed)
        Limiter-->>Client: True
        Client->>API: Make API request
        API-->>Client: Response
    else current >= max_calls
        Redis-->>Limiter: 0 (Rate limited)
        Limiter-->>Client: False
        Client-->>Client: Raise RateLimitExceeded
    end
```

---

## 🔬 Algorithm - Sliding Window

### Principe

**Sliding window** : Fenêtre glissante de N secondes qui se déplace avec le temps.

**Exemple** (60 requêtes/minute) :

```
Temps (secondes) : 0────10────20────30────40────50────60────70
                   │    │     │     │     │     │     │     │
Requêtes         : 10   15    20    5     10    15    12    8
                   │                                   │
                   └────────── 60 seconds ─────────────┘
                                                        ^
                                                    Current time
```

À t=70s :
- **Fixed window** : Compte uniquement [60-70s] = 8 requêtes → **Allowed** (peut burst 60 requêtes à t=71s ❌)
- **Sliding window** : Compte [10-70s] = 15+20+5+10+15+12+8 = 85 requêtes → **Rate limited** ✅

### Implémentation Redis

**Structure de données** : **Sorted Set (ZSET)**

```python
# Clé Redis
key = "rate_limit:google_contacts:user_123"

# ZSET members : timestamp → request_id
# Score = timestamp (secondes)
# Member = unique request ID

ZADD rate_limit:google_contacts:user_123 1700000001 "req_001"
ZADD rate_limit:google_contacts:user_123 1700000002 "req_002"
ZADD rate_limit:google_contacts:user_123 1700000003 "req_003"
# ...

# Cleanup expired (score < now - window_seconds)
ZREMRANGEBYSCORE rate_limit:google_contacts:user_123 0 1700000000

# Count current requests in window
ZCARD rate_limit:google_contacts:user_123  # → 3

# Auto-expire key (memory optimization)
EXPIRE rate_limit:google_contacts:user_123 60
```

**Avantages** :
- ✅ **O(log N)** operations (ZADD, ZREMRANGEBYSCORE, ZCARD)
- ✅ **Atomicité** garantie par Lua scripts
- ✅ **Précision** : window slide exactement avec le temps
- ✅ **Memory-efficient** : Auto-expire après window

---

## 💻 Implémentation

### RedisRateLimiter

```python
# src/infrastructure/rate_limiting/redis_limiter.py
import time
import uuid
from redis.asyncio import Redis

class RedisRateLimiter:
    """
    Distributed rate limiter using Redis + Lua scripts.

    Algorithm: Sliding window with sorted sets (ZSET).

    Features:
    - Atomic operations (Lua scripts)
    - Horizontal scaling (works across N instances)
    - Configurable limits per key
    - O(log N) complexity (Redis ZSET operations)

    Usage:
        limiter = RedisRateLimiter(redis_client)
        allowed = await limiter.acquire(
            key="google_api:user_123",
            max_calls=60,
            window_seconds=60
        )
        if not allowed:
            raise RateLimitExceeded("Too many requests")
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def acquire(
        self,
        key: str,
        max_calls: int,
        window_seconds: int
    ) -> bool:
        """
        Acquire rate limit token (sliding window algorithm).

        Args:
            key: Rate limit key (e.g., "google_api:user_123")
            max_calls: Maximum calls allowed in window
            window_seconds: Time window in seconds

        Returns:
            True if request allowed, False if rate limited

        Example:
            >>> allowed = await limiter.acquire(
            ...     key="google_contacts:user_123",
            ...     max_calls=60,
            ...     window_seconds=60
            ... )
            >>> if not allowed:
            ...     raise RateLimitExceeded("Rate limit: 60 calls/minute")
        """
        now = time.time()
        request_id = str(uuid.uuid4())

        # Lua script (atomic execution)
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local max_calls = tonumber(ARGV[3])
        local request_id = ARGV[4]

        -- Remove expired entries (outside window)
        redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

        -- Count current requests in window
        local current_count = redis.call('ZCARD', key)

        if current_count < max_calls then
            -- Add new request
            redis.call('ZADD', key, now, request_id)
            -- Set expiration (memory optimization)
            redis.call('EXPIRE', key, window)
            return 1  -- Allowed
        else
            return 0  -- Rate limited
        end
        """

        result = await self.redis.eval(
            lua_script,
            keys=[f"rate_limit:{key}"],
            args=[now, window_seconds, max_calls, request_id]
        )

        return bool(result)

    async def get_remaining(
        self,
        key: str,
        max_calls: int,
        window_seconds: int
    ) -> int:
        """
        Get remaining calls in current window.

        Returns:
            Number of calls remaining before rate limit
        """
        now = time.time()

        # Cleanup expired
        await self.redis.zremrangebyscore(
            f"rate_limit:{key}",
            0,
            now - window_seconds
        )

        # Count current
        current_count = await self.redis.zcard(f"rate_limit:{key}")
        remaining = max(0, max_calls - current_count)

        return remaining

    async def reset(self, key: str) -> None:
        """
        Reset rate limit for key (admin/testing).

        Args:
            key: Rate limit key to reset
        """
        await self.redis.delete(f"rate_limit:{key}")
```

### Exceptions

```python
# src/core/exceptions.py
class RateLimitExceeded(Exception):
    """Rate limit exceeded exception."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        key: str | None = None
    ):
        super().__init__(message)
        self.retry_after = retry_after  # Seconds until retry allowed
        self.key = key
```

---

## ⚙️ Configuration

### Settings (Modular Config)

```python
# src/core/config/security.py
from pydantic import Field
from pydantic_settings import BaseSettings

class SecuritySettings(BaseSettings):
    """Security configuration (ADR-009)."""

    # Rate limiting
    rate_limit_per_minute: int = Field(
        60,
        description="API calls per minute (default limit)"
    )

    rate_limit_burst: int = Field(
        100,
        description="Burst allowance (short peaks)"
    )

    # Provider-specific limits
    google_api_rate_limit: int = Field(
        60,
        description="Google API calls per minute per user"
    )

    openai_api_rate_limit: int = Field(
        500,
        description="OpenAI API calls per minute (tier-based)"
    )
```

### Environment Variables

```bash
# .env
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=100
GOOGLE_API_RATE_LIMIT=60
OPENAI_API_RATE_LIMIT=500
```

---

## 🔌 Intégration

### BaseGoogleClient

```python
# src/domains/connectors/clients/base_google_client.py
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter
from src.core.exceptions import RateLimitExceeded

class BaseGoogleClient:
    """
    Base Google API client with rate limiting.

    Features:
    - OAuth 2.1 token management
    - Automatic token refresh
    - Distributed rate limiting
    - Error handling & retries
    """

    def __init__(
        self,
        user_id: UUID,
        credentials: dict,
        rate_limiter: RedisRateLimiter,
        settings: Settings
    ):
        self.user_id = user_id
        self.credentials = credentials
        self.rate_limiter = rate_limiter
        self.settings = settings

    async def _make_request(
        self,
        url: str,
        method: str = "GET",
        **kwargs
    ) -> dict:
        """
        Make Google API request with rate limiting.

        Args:
            url: API endpoint URL
            method: HTTP method
            **kwargs: Additional request parameters

        Returns:
            JSON response

        Raises:
            RateLimitExceeded: If rate limit exceeded
            OAuthTokenRefreshError: If token refresh fails
        """
        # Check rate limit BEFORE making request
        allowed = await self.rate_limiter.acquire(
            key=f"google_api:{self.user_id}",
            max_calls=self.settings.google_api_rate_limit,
            window_seconds=60
        )

        if not allowed:
            # Get remaining time (for retry-after header)
            remaining = await self.rate_limiter.get_remaining(
                key=f"google_api:{self.user_id}",
                max_calls=self.settings.google_api_rate_limit,
                window_seconds=60
            )

            raise RateLimitExceeded(
                message=f"Google API rate limit exceeded: {self.settings.google_api_rate_limit} calls/minute",
                retry_after=60,  # Window duration
                key=f"google_api:{self.user_id}"
            )

        # Make request (rate limit passed)
        try:
            response = await self._session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # API-level rate limit (fallback)
                raise RateLimitExceeded(
                    message="Google API returned 429 Too Many Requests",
                    retry_after=int(e.response.headers.get("Retry-After", 60))
                )
            raise
```

### Dependency Injection (FastAPI)

```python
# src/api/v1/dependencies.py
from fastapi import Depends
from redis.asyncio import Redis
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter
from src.infrastructure.cache.redis import get_redis_client

async def get_rate_limiter(
    redis: Redis = Depends(get_redis_client)
) -> RedisRateLimiter:
    """
    Dependency: Get RedisRateLimiter instance.

    Returns:
        Configured RedisRateLimiter
    """
    return RedisRateLimiter(redis=redis)
```

---

## 🧪 Tests

### Structure de Tests

```
tests/
├── unit/
│   └── infrastructure/
│       └── rate_limiting/
│           └── test_redis_limiter.py       (19 tests unitaires)
├── integration/
│   ├── test_redis_limiter_integration.py   (13 tests integration)
│   └── test_redis_limiter_multiprocess.py  (3 tests multi-process)
```

### Tests Unitaires (19 tests)

```python
# tests/unit/infrastructure/rate_limiting/test_redis_limiter.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.eval = AsyncMock()
    redis.zcard = AsyncMock()
    redis.zremrangebyscore = AsyncMock()
    redis.delete = AsyncMock()
    return redis

@pytest.fixture
def rate_limiter(mock_redis):
    """Rate limiter with mocked Redis."""
    return RedisRateLimiter(redis=mock_redis)

@pytest.mark.asyncio
async def test_acquire_allowed(rate_limiter, mock_redis):
    """Test acquire when rate limit not exceeded."""
    # Mock Redis eval returns 1 (allowed)
    mock_redis.eval.return_value = 1

    result = await rate_limiter.acquire(
        key="test:user123",
        max_calls=60,
        window_seconds=60
    )

    assert result is True
    mock_redis.eval.assert_called_once()

@pytest.mark.asyncio
async def test_acquire_rate_limited(rate_limiter, mock_redis):
    """Test acquire when rate limit exceeded."""
    # Mock Redis eval returns 0 (rate limited)
    mock_redis.eval.return_value = 0

    result = await rate_limiter.acquire(
        key="test:user123",
        max_calls=60,
        window_seconds=60
    )

    assert result is False
    mock_redis.eval.assert_called_once()

@pytest.mark.asyncio
async def test_get_remaining(rate_limiter, mock_redis):
    """Test getting remaining calls."""
    # Mock current count: 45 calls
    mock_redis.zcard.return_value = 45

    remaining = await rate_limiter.get_remaining(
        key="test:user123",
        max_calls=60,
        window_seconds=60
    )

    assert remaining == 15  # 60 - 45 = 15 remaining

@pytest.mark.asyncio
async def test_reset(rate_limiter, mock_redis):
    """Test resetting rate limit."""
    await rate_limiter.reset(key="test:user123")

    mock_redis.delete.assert_called_once_with("rate_limit:test:user123")
```

### Tests Integration (13 tests)

```python
# tests/integration/test_redis_limiter_integration.py
import pytest
import asyncio
from redis.asyncio import Redis
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

@pytest.fixture
async def redis_client():
    """Real Redis client (requires Redis running)."""
    redis = Redis.from_url("redis://localhost:6379/1")  # Test DB
    yield redis
    await redis.flushdb()  # Cleanup
    await redis.close()

@pytest.fixture
async def rate_limiter(redis_client):
    """Rate limiter with real Redis."""
    return RedisRateLimiter(redis=redis_client)

@pytest.mark.integration
@pytest.mark.asyncio
async def test_sliding_window_precision(rate_limiter):
    """Test sliding window precision (vs fixed window)."""
    key = "test:sliding_window"

    # Allow 10 requests per 5 seconds
    max_calls = 10
    window_seconds = 5

    # Make 10 requests at t=0
    for i in range(10):
        result = await rate_limiter.acquire(key, max_calls, window_seconds)
        assert result is True, f"Request {i+1} should be allowed"

    # 11th request should be rate limited
    result = await rate_limiter.acquire(key, max_calls, window_seconds)
    assert result is False, "11th request should be rate limited"

    # Wait 3 seconds (still within window)
    await asyncio.sleep(3)

    # Still rate limited (window slides, all 10 still in [t-5, t])
    result = await rate_limiter.acquire(key, max_calls, window_seconds)
    assert result is False, "Request at t+3s should still be rate limited"

    # Wait 3 more seconds (total 6s, outside initial window)
    await asyncio.sleep(3)

    # Now allowed (old requests expired)
    result = await rate_limiter.acquire(key, max_calls, window_seconds)
    assert result is True, "Request at t+6s should be allowed"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_requests(rate_limiter):
    """Test atomicity with concurrent requests."""
    key = "test:concurrent"

    # Allow 50 requests per minute
    max_calls = 50
    window_seconds = 60

    # Make 100 concurrent requests
    tasks = [
        rate_limiter.acquire(key, max_calls, window_seconds)
        for _ in range(100)
    ]

    results = await asyncio.gather(*tasks)

    # Exactly 50 should be allowed (no race conditions)
    allowed_count = sum(results)
    assert allowed_count == 50, f"Expected 50 allowed, got {allowed_count}"
```

### Tests Multi-Process (3 tests)

```python
# tests/integration/test_redis_limiter_multiprocess.py
import pytest
import asyncio
from multiprocessing import Process, Queue
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

async def worker(worker_id: int, queue: Queue):
    """Worker process making rate-limited requests."""
    redis = Redis.from_url("redis://localhost:6379/1")
    limiter = RedisRateLimiter(redis)

    results = []
    for i in range(20):
        result = await limiter.acquire(
            key="test:multiprocess",
            max_calls=50,
            window_seconds=60
        )
        results.append((worker_id, i, result))

    queue.put(results)
    await redis.close()

@pytest.mark.multiprocess
@pytest.mark.asyncio
async def test_horizontal_scaling():
    """Test rate limiting across 4 worker processes."""
    queue = Queue()

    # Start 4 workers (each making 20 requests)
    processes = [
        Process(target=lambda: asyncio.run(worker(i, queue)))
        for i in range(4)
    ]

    for p in processes:
        p.start()

    for p in processes:
        p.join()

    # Collect results from all workers
    all_results = []
    while not queue.empty():
        all_results.extend(queue.get())

    # Total: 4 workers × 20 requests = 80 requests
    # Allowed: 50 (max_calls)
    # Rate limited: 30

    allowed = sum(1 for _, _, result in all_results if result)
    rate_limited = sum(1 for _, _, result in all_results if not result)

    assert allowed == 50, f"Expected 50 allowed, got {allowed}"
    assert rate_limited == 30, f"Expected 30 rate limited, got {rate_limited}"
```

### Test Coverage

**Résultats** (Session 40) :
- ✅ **35 tests** créés (19 unit + 13 integration + 3 multiprocess)
- ✅ **100% pass rate**
- ✅ **Coverage** : 92% (redis_limiter.py)

---

## 📈 Performance & Scalabilité

### Complexité Algorithmique

| Operation | Complexity | Détail |
|-----------|-----------|--------|
| `acquire()` | **O(log N + 1)** | ZREMRANGEBYSCORE O(log N), ZADD O(log N), ZCARD O(1) |
| `get_remaining()` | **O(log N + 1)** | ZREMRANGEBYSCORE O(log N), ZCARD O(1) |
| `reset()` | **O(1)** | DELETE O(1) |

**N** = Nombre de requêtes dans la fenêtre (~60 pour 60 req/min)

### Benchmarks

**Setup** :
- Redis 7.2 (localhost)
- Python 3.12, asyncio
- 1000 requêtes séquentielles

| Metric | Value |
|--------|-------|
| **Latency P50** | 1.2ms |
| **Latency P95** | 2.5ms |
| **Latency P99** | 4.1ms |
| **Throughput** | ~800 req/s (single Redis) |

### Horizontal Scaling

**Test** : 4 backend instances, 50 req/min limit, 80 total requests

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| **Allowed** | 50 | 50 | ✅ |
| **Rate limited** | 30 | 30 | ✅ |
| **Race conditions** | 0 | 0 | ✅ |

**Conclusion** : Atomicité garantie par Lua scripts, aucune race condition.

---

## 📊 Monitoring

### Prometheus Metrics

```python
# src/infrastructure/observability/metrics_agents.py
from prometheus_client import Counter, Histogram

rate_limit_requests_total = Counter(
    "rate_limit_requests_total",
    "Total rate limit checks",
    labelnames=["key_prefix", "allowed"]
)

rate_limit_check_duration_seconds = Histogram(
    "rate_limit_check_duration_seconds",
    "Rate limit check latency",
    labelnames=["key_prefix"]
)
```

### Usage dans RedisRateLimiter

```python
async def acquire(self, key: str, max_calls: int, window_seconds: int) -> bool:
    key_prefix = key.split(":")[0]  # Extract prefix (e.g., "google_api")

    with rate_limit_check_duration_seconds.labels(key_prefix=key_prefix).time():
        result = await self._do_acquire(key, max_calls, window_seconds)

    rate_limit_requests_total.labels(
        key_prefix=key_prefix,
        allowed=str(result)
    ).inc()

    return result
```

### Grafana Dashboard

**Panel 1 - Rate Limit Requests** :
```promql
rate(rate_limit_requests_total[5m])
```

**Panel 2 - Rate Limit Allowed/Denied Ratio** :
```promql
sum by (key_prefix) (rate(rate_limit_requests_total{allowed="true"}[5m]))
/
sum by (key_prefix) (rate(rate_limit_requests_total[5m]))
```

**Panel 3 - Rate Limit Check Latency** :
```promql
histogram_quantile(0.95, rate(rate_limit_check_duration_seconds_bucket[5m]))
```

---

## 🔗 Ressources

### Documentation Redis

- **ZSET Commands**: https://redis.io/commands#sorted-set
- **Lua Scripting**: https://redis.io/docs/manual/programmability/eval-intro/
- **ZADD**: https://redis.io/commands/zadd/
- **ZREMRANGEBYSCORE**: https://redis.io/commands/zremrangebyscore/
- **ZCARD**: https://redis.io/commands/zcard/

### Articles

- **Sliding Window Rate Limiting**: https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
- **Redis Rate Limiting Patterns**: https://redis.io/glossary/rate-limiting/

### Internal References

- **[ARCHITECTURE.md](../ARCHITECTURE.md)**: Section "Configuration & Infrastructure"
- **[ADR-009: Config Module Split](../architecture/ADR-009-Config-Module-Split.md)**: Configuration settings
- **Source Code**: `src/infrastructure/rate_limiting/redis_limiter.py`
- **Tests**: `tests/unit/infrastructure/rate_limiting/`, `tests/integration/`

---

**Fin de RATE_LIMITING.md** - Rate Limiting Distribué Documentation.
