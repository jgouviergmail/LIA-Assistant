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

### Cycle Reset (single source of truth)

`UserStatistics.cycle_*` fields are reset by **one** method — `UserStatistics.reset_cycle(cycle_start)` — which zeroes **every** `cycle_*` column by introspecting the model (tokens, cost, messages, Google API, image generation, STT, TTS). The three code paths that can cross a billing-cycle boundary all delegate to it: a chat message (`UserStatisticsRepository.create_or_update`), an STT call (`add_stt_usage`), and a dashboard read (`StatisticsService.reset_cycle_if_needed`). This closes a class of bug where each path hand-reset a *different subset* of counters and the others leaked across the boundary (audit wave 2, ADR-095). A new `cycle_*` column is reset automatically; a coverage-sentinel unit test fails if one is added without multi-silo test coverage.

### Cycle Stale Detection

The reset is only *applied* when an event actually crosses the boundary. If a user hasn't sent a message (or triggered any of the three paths) since the cycle rollover, the cached cycle data is stale. The `_is_cycle_stale()` method detects this by comparing `stats.current_cycle_start` with the theoretical current cycle start.

## Warning before the wall (A5)

The backend already computed a graded `status` (`ok` / `warning` ≥ 80 % /
`critical` ≥ 95 % / `blocked_*`) and six per-dimension usages. The chat read
exactly two fields — `is_blocked` and `block_reason` — so everything else was
fetched, polled every 60 s and thrown away. The user met a wall with no warning.

`usageWarningOf()` (`lib/usage-warning.ts`) is the pure rule:

- returns `null` when the account is **already blocked** — the blocking banner
  owns that state, and two messages about the same limit would be noise;
- picks the **binding** dimension, meaning the highest percentage: any single
  dimension blocks the whole account, so naming a lower one would point at the
  wrong deadline;
- returns `cycleEnd` only for a `cycle_*` dimension — an absolute limit does not
  reset, and promising a reset date for one would be a lie;
- returns `null` when the status says `warning` but no dimension reports a
  percentage: trust the dimensions, not the label.

`UsageBanners` owns the mutual exclusion (blocked wins, always), which keeps the
"never both" rule inside one component instead of two independent conditions in
the page.

## What the ceilings cover, and who pays (ADR-272)

Two ceilings bound every token the **platform** pays for: what one account may
consume, and what the instance may spend in a day. Only what a person pays with
their OWN connector key is outside them.

`domains/usage_limits/cost_bearers.py` draws that line, family by family, and it
is the declaration a guard checks in BOTH directions. `provider_api_keys` has no
`user_id`, so the LLM, TTS, STT, image and Maps families run on the deployment's
credential and carry `CostBearer.INSTANCE`; Perplexity, Brave, the weather
connector and telephony run on the person's own credential and carry
`CostBearer.USER`. An instance-paid family missing from the enforced sum is a
spend no ceiling sees; a user-paid family present in it charges someone twice.

### One guard, and every door is named

`infrastructure/llm/usage_guard.py` is the single usage guard, and
`LLM_CHOKEPOINTS` names every door it must sit on. Three shapes had produced
five unbounded spend sites out of the forty-six `LLM_SPEND_ROADS` declares:

1. **A chokepoint is the INNERMOST door, never its wrapper.** The registry named
   `get_structured_output_with_retry` while nine modules called
   `get_structured_output` directly — one of two siblings in the same file — and
   the completeness test could not see it, because it only checks DECLARED doors.
2. **A gate that returns early bounds nothing.** The shared guard short-circuited
   on `usage_limits_enabled`, which switches off the INSTANCE ceiling too
   (`check_user_allowed` deliberately keeps that one outside the flag), and on a
   call having no owner — true of the account's ceiling, and beside the point for
   the deployment credential that actually paid.
3. **One refusal, two answers.** The router named an instance pause with a code
   and a `Retry-After`; the shared guard answered with neither.

Two refusals the guard must NOT make: a call with no owner is never blocked (its
bound is the instance ledger), and `"system"` is not an account.

### How a caller receives a refusal follows its transport

The verdict never does. `domains/usage_limits/enforcement.py` holds one raiser
and its non-raising twin:

| Path | Function | Behaviour |
|---|---|---|
| Request | `enforce_usage_limit` / `raise_for_blocked_verdict` | Raises — HTTP 429, a dedicated code, and a `Retry-After` naming when the pause lifts |
| Background | `spend_blocked` | Degrades — the reminder still fires, the dashboard still renders, and it logs **skipped**, never *failed* |

A quota refusal is not a generation failure, and reporting it as one sends an
operator looking for a fault that does not exist.

`test_every_spend_site_is_bounded` walks the registry and refuses a site that
reaches no ceiling; `test_usage_guard_at_every_chokepoint` refuses an unguarded
door; `test_cost_bearer_declaration` compares the declaration to the sum
`_build_user_stats_columns` actually enforces, read by AST.

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
- ADR: [ADR-270 — Spend roads, cost bearers, register authorship](../architecture/ADR-270-Spend-Roads-And-Register-Authorship.md)
- ADR: [ADR-272 — Every platform-paid token answers to both ceilings](../architecture/ADR-272-Every-Platform-Paid-Token-Answers-To-Both-Ceilings.md)
- Plan: `~/.claude/plans/wiggly-mapping-pillow.md`
