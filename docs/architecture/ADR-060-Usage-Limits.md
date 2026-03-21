# ADR-060: Per-User Usage Limits

## Status
Accepted

## Date
2026-03-21

## Context
LIA's multi-agent architecture makes LLM calls and connector API requests that incur real costs (OpenAI, Anthropic, Google APIs). Without usage controls, any registered user can consume unlimited resources, creating an uncontrolled financial risk for the operator.

## Decision
Implement a per-user usage limits system with:

### Limit Dimensions
- **Tokens** (prompt + completion combined) — per billing cycle and/or absolute
- **Messages** (user message count) — per billing cycle and/or absolute
- **Cost** (EUR) — per billing cycle and/or absolute

Each dimension can be set to a numeric value or `null` (unlimited).

### Billing Cycle
Monthly rolling cycle aligned with user account creation date (reuses existing `StatisticsService.calculate_cycle_start()` logic from the dashboard).

### Defense in Depth (5 Layers)
| Layer | Location | Mechanism |
|-------|----------|-----------|
| 0 | Chat Router (`agents/api/router.py`) | HTTP 429 before SSE stream |
| 1 | Agent Service (`agents/api/service.py`) | SSE error chunk (covers scheduled actions) |
| 2 | LLM Invocation (`infrastructure/llm/invoke_helpers.py`) | Guard in `invoke_with_instrumentation()` |
| 3 | Proactive Runner (`infrastructure/proactive/runner.py`) | Skip blocked users |
| 4 | Migration of direct `.ainvoke()` calls | Reminder notification, voice service |

### Caching
Redis cache with 60s TTL on check results. Invalidated after token persistence and admin updates.

### Admin Management
- REST API for CRUD operations on user limits
- WebSocket endpoint for real-time gauge updates
- Manual block/unblock with reason tracking

## Architecture
- New DDD domain: `src/domains/usage_limits/`
- Table: `user_usage_limits` (1:1 with `users`, FK CASCADE)
- No data migration for existing users (no record = unlimited)
- Feature-flagged via `USAGE_LIMITS_ENABLED`

## Consequences
- Operators can control costs per user
- 5-layer enforcement prevents any bypass
- Fail-open design: infrastructure failures don't block users
- New LLM-calling services using `invoke_with_instrumentation()` are automatically protected
