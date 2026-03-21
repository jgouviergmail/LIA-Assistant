# Usage Limits — Technical Documentation

## Overview

Per-user usage limits allow administrators to control LLM resource consumption (tokens, messages, cost) for each registered user. The system provides multi-layer enforcement, real-time monitoring, and admin management tools.

## Architecture

### Domain Structure
```
src/domains/usage_limits/
├── __init__.py          # Module exports
├── models.py            # UserUsageLimit SQLAlchemy model
├── schemas.py           # Pydantic v2 request/response schemas
├── repository.py        # Data access with JOINs (users + user_statistics)
├── service.py           # Business logic (enforcement + admin CRUD)
├── router.py            # REST API endpoints
├── ticket_store.py      # Redis-based WebSocket auth tickets
└── websocket.py         # Admin real-time dashboard WebSocket
```

### Database

**Table: `user_usage_limits`** (1:1 with `users`)

| Column | Type | Description |
|--------|------|-------------|
| `token_limit_per_cycle` | BigInteger | Monthly token limit (null = unlimited) |
| `message_limit_per_cycle` | BigInteger | Monthly message limit |
| `cost_limit_per_cycle` | Numeric(12,6) | Monthly cost limit (EUR) |
| `token_limit_absolute` | BigInteger | Lifetime token limit |
| `message_limit_absolute` | BigInteger | Lifetime message limit |
| `cost_limit_absolute` | Numeric(12,6) | Lifetime cost limit (EUR) |
| `is_usage_blocked` | Boolean | Admin manual kill switch |
| `blocked_reason` | String(500) | Block reason |

No record = no limits (unlimited). Records are created on-demand by admins or at user registration (with defaults from env vars).

### Enforcement Layers

```
User Message → Layer 0 (Router: HTTP 429)
             → Layer 1 (Service: SSE error)
             → Layer 2 (invoke_with_instrumentation: exception)
             → Layer 3 (Proactive Runner: skip user)
```

**Layer 2** is the most important for robustness — it catches ALL LLM calls that go through `invoke_with_instrumentation()`, including background services (journal extraction, memory extraction, interest processing, etc.).

### Caching

- Redis key: `usage_limit:{user_id}`
- TTL: 60 seconds (configurable via `USAGE_LIMIT_CACHE_TTL_SECONDS`)
- Invalidated after: token persistence, admin limit updates, billing cycle rollover
- Fail-open: if Redis/DB is down, users are allowed through

### Cycle Stale Detection

`UserStatistics.cycle_*` fields are only reset when a user sends a message (`StatisticsService.reset_cycle_if_needed()`). If a user hasn't sent a message since the cycle rollover, the cached cycle data is stale. The `_is_cycle_stale()` method detects this by comparing `stats.current_cycle_start` with the theoretical current cycle start.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/usage-limits/me` | User | Get own limits and usage |
| GET | `/usage-limits/admin/users` | Admin | List all users with limits |
| PUT | `/usage-limits/admin/users/{id}/limits` | Admin | Update user limits |
| PUT | `/usage-limits/admin/users/{id}/block` | Admin | Toggle manual block |
| POST | `/usage-limits/admin/ws/ticket` | Admin | Get WebSocket auth ticket |
| WS | `/usage-limits/admin/ws` | Ticket | Real-time gauge updates |

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `USAGE_LIMITS_ENABLED` | `false` | Feature flag |
| `DEFAULT_TOKEN_LIMIT_PER_CYCLE` | (empty) | Default for new users |
| `DEFAULT_MESSAGE_LIMIT_PER_CYCLE` | (empty) | Default for new users |
| `DEFAULT_COST_LIMIT_PER_CYCLE_EUR` | (empty) | Default for new users |
| `USAGE_LIMIT_CACHE_TTL_SECONDS` | `60` | Redis cache TTL |

## Frontend Integration

- **Dashboard tile**: Shows usage gauges when limits are configured
- **Chat blocking**: Disables input + voice when blocked, shows alert banner
- **Admin section**: Searchable table with inline block toggle + edit modal
- **SSE error**: HTTP 429 and SSE `usage_limit_exceeded` error handling

## References

- ADR: [ADR-060-Usage-Limits](../architecture/ADR-060-Usage-Limits.md)
- Plan: `~/.claude/plans/wiggly-mapping-pillow.md`
