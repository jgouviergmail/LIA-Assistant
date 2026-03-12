"""
WebSocket Ticket Store for BFF Pattern Authentication.

WebSocket connections cannot use HTTP-only cookies directly. This ticket system
provides secure authentication for the /ws/audio endpoint.

Security Features:
- Short-lived tokens (60s TTL by default)
- Single-use (deleted after validation)
- Tied to authenticated session via REST endpoint

Flow:
1. User calls POST /api/v1/voice/ticket (authenticated via session cookie)
2. Backend generates ticket UUID, stores in Redis with TTL
3. Returns ticket to frontend
4. Frontend connects to WebSocket with ?ticket=xxx
5. WebSocket validates ticket, deletes it (single-use), proceeds

Pattern: Similar to OAuth state storage (core/oauth/flow_handler.py)

Reference: plan zippy-drifting-valley.md (section 2.4.4)
Created: 2026-02-01
"""

import json
from uuid import uuid4

from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import WS_TICKET_KEY_PREFIX
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_voice import (
    websocket_tickets_issued_total,
    websocket_tickets_validated_total,
)

logger = get_logger(__name__)


class WebSocketTicketStore:
    """
    Short-lived ticket store for WebSocket authentication.

    Implements the BFF (Backend-for-Frontend) pattern for WebSocket auth.
    Tickets are stored in Redis with automatic expiration.

    Thread-safe: All operations are atomic via Redis.

    Usage:
        redis = await get_redis_session()
        ticket_store = WebSocketTicketStore(redis)

        # Issue ticket (from authenticated REST endpoint)
        ticket = await ticket_store.create_ticket(user_id)

        # Validate ticket (from WebSocket handler)
        user_id = await ticket_store.validate_and_consume_ticket(ticket)
        if not user_id:
            # Reject connection
            pass
    """

    def __init__(self, redis_client: Redis) -> None:
        """
        Initialize ticket store with Redis client.

        Args:
            redis_client: Async Redis client for ticket storage
        """
        self._redis = redis_client
        self._ttl_seconds = settings.voice_ws_ticket_ttl_seconds

    async def create_ticket(self, user_id: str) -> str:
        """
        Create a short-lived WebSocket authentication ticket.

        The ticket is stored in Redis with automatic expiration.
        Single-use: will be deleted upon validation.

        Args:
            user_id: Authenticated user's UUID (from session)

        Returns:
            Ticket string (UUID format) for WebSocket connection
        """
        ticket = str(uuid4())
        key = f"{WS_TICKET_KEY_PREFIX}{ticket}"

        # Store ticket data as JSON
        ticket_data = json.dumps(
            {
                "user_id": user_id,
            }
        )

        await self._redis.setex(
            key,
            self._ttl_seconds,
            ticket_data,
        )

        # Track ticket issuance
        websocket_tickets_issued_total.inc()

        logger.debug(
            "websocket_ticket_created",
            user_id=user_id,
            ticket_prefix=ticket[:8],
            ttl_seconds=self._ttl_seconds,
        )

        return ticket

    async def validate_and_consume_ticket(self, ticket: str) -> str | None:
        """
        Validate ticket and consume it (single-use pattern).

        Atomically retrieves and deletes the ticket to prevent replay attacks.

        Args:
            ticket: Ticket string from WebSocket query param

        Returns:
            user_id if ticket is valid, None if invalid/expired/already-used
        """
        if not ticket:
            websocket_tickets_validated_total.labels(status="invalid").inc()
            logger.warning(
                "websocket_ticket_validation_failed",
                reason="empty_ticket",
            )
            return None

        key = f"{WS_TICKET_KEY_PREFIX}{ticket}"

        # Atomic GET and DELETE using pipeline
        # This ensures ticket cannot be reused even with concurrent requests
        pipe = self._redis.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()

        data = results[0]  # GET result
        deleted = results[1]  # DELETE result (number of keys deleted)

        if not data:
            websocket_tickets_validated_total.labels(status="expired").inc()
            logger.warning(
                "websocket_ticket_validation_failed",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
                reason="not_found_or_expired",
            )
            return None

        try:
            ticket_data = json.loads(data)
            user_id: str = ticket_data["user_id"]

            websocket_tickets_validated_total.labels(status="valid").inc()

            logger.debug(
                "websocket_ticket_validated",
                user_id=user_id,
                ticket_prefix=ticket[:8],
                consumed=deleted > 0,
            )

            return user_id

        except (json.JSONDecodeError, KeyError) as e:
            websocket_tickets_validated_total.labels(status="invalid").inc()
            logger.error(
                "websocket_ticket_parse_error",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def revoke_ticket(self, ticket: str) -> bool:
        """
        Explicitly revoke a ticket before it expires.

        Useful for cleanup scenarios where a ticket was issued
        but the WebSocket connection was never established.

        Args:
            ticket: Ticket string to revoke

        Returns:
            True if ticket was found and deleted, False otherwise
        """
        key = f"{WS_TICKET_KEY_PREFIX}{ticket}"
        deleted = await self._redis.delete(key)

        if deleted > 0:
            logger.debug(
                "websocket_ticket_revoked",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
            )
            return True

        return False
