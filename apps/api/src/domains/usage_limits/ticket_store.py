"""
WebSocket Ticket Store for Admin Usage Limits Dashboard.

Short-lived, single-use ticket authentication for the admin WebSocket
endpoint that pushes real-time usage gauge updates.

Follows the same BFF (Backend-for-Frontend) pattern as the voice ticket store
(src/domains/voice/ticket_store.py) but with its own Redis key prefix and TTL.

Flow:
    1. Admin calls POST /api/v1/usage-limits/admin/ws/ticket (authenticated)
    2. Backend generates ticket UUID, stores in Redis with TTL
    3. Returns ticket to frontend
    4. Frontend connects to WebSocket with ?ticket=xxx
    5. WebSocket validates ticket, deletes it (single-use), proceeds

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from __future__ import annotations

import json
from uuid import uuid4

import structlog
from redis.asyncio import Redis

from src.core.constants import (
    REDIS_KEY_USAGE_LIMIT_WS_TICKET_PREFIX,
    USAGE_LIMIT_WS_TICKET_TTL_SECONDS_DEFAULT,
)

logger = structlog.get_logger(__name__)


class AdminUsageLimitTicketStore:
    """Short-lived ticket store for admin usage limits WebSocket authentication.

    Implements the BFF pattern for WebSocket auth. Tickets are stored in Redis
    with automatic expiration. Thread-safe via atomic Redis operations.

    Usage:
        redis = await get_redis_cache()
        store = AdminUsageLimitTicketStore(redis)

        # Issue ticket (from authenticated REST endpoint)
        ticket = await store.create_ticket(user_id)

        # Validate ticket (from WebSocket handler)
        user_id = await store.validate_and_consume_ticket(ticket)
    """

    def __init__(self, redis_client: Redis) -> None:
        """Initialize ticket store with Redis client.

        Args:
            redis_client: Async Redis client for ticket storage.
        """
        self._redis = redis_client
        self._ttl_seconds = USAGE_LIMIT_WS_TICKET_TTL_SECONDS_DEFAULT

    async def create_ticket(self, user_id: str) -> str:
        """Create a short-lived WebSocket authentication ticket.

        The ticket is stored in Redis with automatic expiration.
        Single-use: will be deleted upon validation.

        Args:
            user_id: Authenticated admin user's UUID string.

        Returns:
            Ticket string (UUID format) for WebSocket connection.
        """
        ticket = str(uuid4())
        key = f"{REDIS_KEY_USAGE_LIMIT_WS_TICKET_PREFIX}{ticket}"

        ticket_data = json.dumps({"user_id": user_id})

        await self._redis.setex(key, self._ttl_seconds, ticket_data)

        logger.debug(
            "usage_limit_ws_ticket_created",
            user_id=user_id,
            ticket_prefix=ticket[:8],
            ttl_seconds=self._ttl_seconds,
        )

        return ticket

    async def validate_and_consume_ticket(self, ticket: str) -> str | None:
        """Validate ticket and consume it (single-use pattern).

        Atomically retrieves and deletes the ticket to prevent replay attacks.

        Args:
            ticket: Ticket string from WebSocket query param.

        Returns:
            user_id if ticket is valid, None if invalid/expired/already-used.
        """
        if not ticket:
            logger.warning(
                "usage_limit_ws_ticket_validation_failed",
                reason="empty_ticket",
            )
            return None

        key = f"{REDIS_KEY_USAGE_LIMIT_WS_TICKET_PREFIX}{ticket}"

        # Atomic GET and DELETE using pipeline
        pipe = self._redis.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()

        data = results[0]  # GET result

        if not data:
            logger.warning(
                "usage_limit_ws_ticket_validation_failed",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
                reason="not_found_or_expired",
            )
            return None

        try:
            ticket_data = json.loads(data)
            user_id: str = ticket_data["user_id"]

            logger.debug(
                "usage_limit_ws_ticket_validated",
                user_id=user_id,
                ticket_prefix=ticket[:8],
            )

            return user_id

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                "usage_limit_ws_ticket_parse_error",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None
