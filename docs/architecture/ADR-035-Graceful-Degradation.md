# ADR-035: Graceful Degradation

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Resilience patterns for production reliability
**Related Documentation**: `docs/technical/RESILIENCE.md`

---

## Context and Problem Statement

L'application multi-services nécessitait une résilience robuste :

1. **Circuit Breakers** : Protection contre services défaillants
2. **Retry Logic** : Gestion des erreurs transitoires
3. **Fallbacks** : Continuité de service dégradée
4. **Health Monitoring** : Détection proactive des pannes

**Question** : Comment maintenir le service quand des composants échouent ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Circuit Breakers** : Prévention cascade failures
2. **Retry with Backoff** : Exponential backoff pour transients
3. **Health Endpoints** : Monitoring des dépendances
4. **Fail-Open** : Préférence availability sur strictness

### Nice-to-Have:

- Model fallback middleware
- Partial error handling
- Connection pool monitoring

---

## Decision Outcome

**Chosen option**: "**Circuit Breakers + Retry + Fail-Open + Health Checks**"

### Architecture Overview

```mermaid
graph TB
    subgraph "CIRCUIT BREAKER"
        CB[CircuitBreaker<br/>CLOSED → OPEN → HALF_OPEN]
        CB_CFG[Config<br/>5 failures → open<br/>60s timeout<br/>3 successes → close]
    end

    subgraph "RETRY LOGIC"
        RETRY[retry_with_backoff<br/>3 attempts<br/>2.0x factor]
        RETRY_LLM[LLM Retry<br/>2s → 4s → 8s]
        RETRY_TOOL[Tool Retry<br/>1.5s → 2.25s → 3.4s]
    end

    subgraph "FALLBACKS"
        FB_MODEL[Model Fallback<br/>claude → deepseek]
        FB_RATE[Rate Limit Fallback<br/>Redis → local]
        FB_CACHE[Cache Fallback<br/>TTL-based defaults]
    end

    subgraph "HEALTH MONITORING"
        HEALTH[/health endpoint<br/>Redis + DB status]
        POOL[Connection Pool<br/>Exhaustion tracking]
        BG[Background Tasks<br/>Graceful shutdown]
    end

    style CB fill:#4CAF50,stroke:#2E7D32,color:#fff
    style RETRY fill:#2196F3,stroke:#1565C0,color:#fff
    style FB_MODEL fill:#FF9800,stroke:#F57C00,color:#fff
```

### Circuit Breaker Implementation

```python
# apps/api/src/infrastructure/resilience/circuit_breaker.py

class CircuitBreaker:
    """Three-state circuit breaker pattern."""

    CLOSED = "closed"    # Normal operation
    OPEN = "open"        # Failing, reject immediately
    HALF_OPEN = "half_open"  # Testing recovery

    async def execute(self, func, *args, **kwargs):
        if self.state == self.OPEN:
            if self._can_attempt_reset():
                self.state = self.HALF_OPEN
            else:
                raise CircuitOpenError("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

**Configuration** (`apps/api/src/core/config/connectors.py`):
```python
circuit_breaker_failure_threshold: int = 5      # Failures to open
circuit_breaker_success_threshold: int = 3      # Successes to close
circuit_breaker_timeout_seconds: int = 60       # Open duration
circuit_breaker_half_open_max_calls: int = 3    # Test calls
```

### Retry with Exponential Backoff

```python
# apps/api/src/infrastructure/utils/retry.py

@retry_with_backoff(
    max_retries=3,
    backoff_factor=2.0,
    retryable_exceptions=(httpx.TimeoutException, httpx.ConnectError)
)
async def make_api_call():
    # Retry pattern: 2s → 4s → 8s
    ...
```

**LLM Middleware Configuration**:
```python
enable_retry_middleware: bool = True
retry_max_attempts: int = 3
retry_backoff_factor: float = 2.0  # 2s, 4s, 8s
```

### Model Fallback Middleware

```python
# apps/api/src/core/config/agents.py

enable_fallback_middleware: bool = True
fallback_models: str = "claude-sonnet-4-5,deepseek-chat"

# Triggers on: 429 (rate limit), 500-504 (service errors), timeouts
```

### Health Check Endpoint

```python
# apps/api/src/main.py

@app.get("/health")
async def health_check():
    redis_status = await check_redis_health()
    db_status = await check_database_health()

    if redis_status == "healthy" and db_status == "healthy":
        status = "healthy"
        status_code = 200
    elif redis_status == "unhealthy" and db_status == "unhealthy":
        status = "unhealthy"
        status_code = 503
    else:
        status = "degraded"
        status_code = 200

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "checks": {"redis": redis_status, "database": db_status},
        }
    )
```

### Fail-Open Patterns

```python
# Semantic validation timeout (fail-open)
semantic_validation_timeout_seconds: float = 10.0
# If timeout → assume plan valid (performance > strictness)

# Rate limiting (fail-open)
async def acquire(self, key, max_calls, window_seconds):
    try:
        return await self._redis_acquire(...)
    except Exception:
        logger.warning("Redis unavailable, allowing request")
        return True  # Fail-open
```

### Partial Error Handler

```python
# apps/api/src/core/partial_error_handler.py

class PartialErrorHandler:
    """Handle partial domain failures gracefully."""

    def handle_error(self, domain: str, error: Exception, language: str = "fr"):
        category = self._classify_error(error)

        return DomainErrorContext(
            domain=domain,
            category=category,  # RATE_LIMIT, TIMEOUT, AUTH, etc.
            severity=self._get_severity(category),
            recovery_action=self._get_recovery(category),
            user_message=self._get_i18n_message(category, language),
        )
```

**Error Categories**:
| Category | Severity | Recovery |
|----------|----------|----------|
| RATE_LIMIT | MEDIUM | WAIT |
| TIMEOUT | MEDIUM | RETRY |
| AUTHENTICATION | HIGH | REAUTHENTICATE |
| NETWORK | MEDIUM | RETRY |
| NOT_FOUND | LOW | MODIFY_QUERY |

### Connection Pool Monitoring

```python
# apps/api/src/infrastructure/database/session.py

# Metrics tracked
db_connection_pool_checkedout      # Current in-use
db_connection_pool_size            # Configured size
db_connection_pool_overflow        # Temporary overflow
db_connection_pool_exhausted_total # Exhaustion events
```

### Background Task Safety

```python
# apps/api/src/infrastructure/async_utils.py

def safe_fire_and_forget(coro, name: str | None = None):
    """
    Launch background task without blocking response.

    - Keeps strong reference (prevents GC)
    - Logs exceptions on failure
    - Tracks active task count
    """
    task = asyncio.create_task(coro)
    _active_tasks.add(task)
    task.add_done_callback(_task_done_callback)
    return task

async def wait_all_background_tasks(timeout: float = 30.0):
    """Graceful shutdown with timeout."""
```

### Fail-Open vs Fail-Close

| Scenario | Decision | Rationale |
|----------|----------|-----------|
| Semantic validation timeout | **Fail-Open** | Performance > strictness |
| Redis unavailable | **Fail-Open** | Allow requests |
| LLM config invalid | **Fail-Close** | Startup safety |
| Database exhaustion | **Fail-Close** | Data integrity |
| Background tasks | **Fail-Open** | Non-blocking |

### Consequences

**Positive**:
- ✅ **Circuit Breakers** : Prevents cascade failures
- ✅ **Retry + Backoff** : Handles transient errors
- ✅ **Model Fallback** : LLM provider resilience
- ✅ **Health Checks** : Proactive monitoring
- ✅ **Fail-Open** : Availability prioritized
- ✅ **Partial Errors** : Graceful degradation

**Negative**:
- ⚠️ Fail-open may allow invalid requests
- ⚠️ Circuit breaker tuning required

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Circuit breaker (3 states)
- [x] ✅ Retry with exponential backoff
- [x] ✅ Model fallback middleware
- [x] ✅ Health check endpoint
- [x] ✅ Fail-open for semantic validation
- [x] ✅ Connection pool monitoring
- [x] ✅ Background task safety

---

## References

### Source Code
- **Circuit Breaker**: `apps/api/src/infrastructure/resilience/circuit_breaker.py`
- **Retry Utils**: `apps/api/src/infrastructure/utils/retry.py`
- **Partial Errors**: `apps/api/src/core/partial_error_handler.py`
- **Async Utils**: `apps/api/src/infrastructure/async_utils.py`
- **Database Session**: `apps/api/src/infrastructure/database/session.py`

---

**Fin de ADR-035** - Graceful Degradation Decision Record.
