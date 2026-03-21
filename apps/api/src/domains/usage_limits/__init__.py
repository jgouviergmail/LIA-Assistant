"""
Usage limits domain — Per-user usage quota management.

Provides per-user limits on tokens, messages, and cost with multi-layer
enforcement (router, service, LLM invocation guard, proactive runner).
Admins can configure limits, manually block users, and monitor usage
in real-time via WebSocket.

Components:
    - models: SQLAlchemy model (UserUsageLimit)
    - schemas: Pydantic request/response schemas + UsageLimitStatus enum
    - repository: Data access with complex JOINs (users + user_statistics)
    - service: Business logic (check_user_allowed, CRUD, cache management)
    - router: FastAPI endpoints (user /me + admin CRUD)
    - ticket_store: Redis-based WebSocket auth ticket store
    - websocket: Admin real-time gauge updates

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""
