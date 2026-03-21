"""
WebSocket endpoint for admin usage limits real-time dashboard.

Pushes periodic updates of user usage stats to connected admin clients.
Uses ticket-based authentication (same BFF pattern as voice WebSocket).

Protocol:
    1. Admin gets ticket via POST /usage-limits/admin/ws/ticket
    2. Connect with ?ticket=<ticket>
    3. Server pushes stats_update every USAGE_LIMIT_WS_PUSH_INTERVAL_SECONDS
    4. Client can send {"type": "ping"} for keepalive
    5. Idle timeout after USAGE_LIMIT_WS_IDLE_TIMEOUT_SECONDS

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket
from starlette.websockets import WebSocketDisconnect

from src.core.constants import (
    USAGE_LIMIT_WS_IDLE_TIMEOUT_SECONDS,
    USAGE_LIMIT_WS_PUSH_INTERVAL_SECONDS,
    USAGE_LIMIT_WS_TICKET_TTL_SECONDS_DEFAULT,
)
from src.core.session_dependencies import get_current_superuser_session
from src.domains.auth.models import User
from src.domains.usage_limits.schemas import WebSocketTicketResponse
from src.domains.usage_limits.ticket_store import AdminUsageLimitTicketStore
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/usage-limits", tags=["Usage Limits"])


# ============================================================================
# WebSocket Ticket Endpoint
# ============================================================================


@router.post(
    "/admin/ws/ticket",
    response_model=WebSocketTicketResponse,
    summary="Generate admin WebSocket ticket",
    description="Generate a short-lived, single-use ticket for admin WebSocket authentication.",
)
async def create_admin_ws_ticket(
    current_user: User = Depends(get_current_superuser_session),
) -> WebSocketTicketResponse:
    """Generate a WebSocket authentication ticket for admin usage dashboard.

    Args:
        current_user: Authenticated superuser.

    Returns:
        WebSocketTicketResponse with ticket and TTL.
    """
    redis = await get_redis_cache()
    ticket_store = AdminUsageLimitTicketStore(redis)

    ticket = await ticket_store.create_ticket(str(current_user.id))

    logger.info(
        "usage_limit_ws_ticket_issued",
        user_id=str(current_user.id),
        ticket_prefix=ticket[:8],
    )

    return WebSocketTicketResponse(
        ticket=ticket,
        ttl_seconds=USAGE_LIMIT_WS_TICKET_TTL_SECONDS_DEFAULT,
    )


# ============================================================================
# WebSocket Endpoint
# ============================================================================


@router.websocket("/admin/ws")
async def admin_usage_ws(
    websocket: WebSocket,
    ticket: Annotated[str, Query(description="WebSocket authentication ticket")],
) -> None:
    """WebSocket endpoint for real-time admin usage limits dashboard.

    Protocol:
        1. Connect with ?ticket=<ticket> from POST /usage-limits/admin/ws/ticket
        2. Server validates ticket, accepts connection
        3. Server pushes stats every USAGE_LIMIT_WS_PUSH_INTERVAL_SECONDS
        4. Client can send {"type": "ping"} for keepalive
        5. Connection closed on idle timeout or client disconnect

    Close Codes:
        - 4001: Invalid or expired ticket
        - 4008: Idle timeout
        - 1000: Normal close

    Args:
        websocket: FastAPI WebSocket connection.
        ticket: Single-use authentication ticket from query param.
    """
    user_id: str | None = None

    try:
        # 1. Authenticate via ticket (BFF pattern)
        redis = await get_redis_cache()
        ticket_store = AdminUsageLimitTicketStore(redis)

        user_id = await ticket_store.validate_and_consume_ticket(ticket)

        if not user_id:
            logger.warning(
                "usage_limit_ws_auth_failed",
                reason="invalid_ticket",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
            )
            await websocket.close(code=4001, reason="Invalid or expired ticket")
            return

        # 2. Accept connection
        await websocket.accept()
        logger.info(
            "usage_limit_ws_connected",
            user_id=user_id,
        )

        # 3. Main loop: push stats + handle client messages
        last_activity = time.time()

        while True:
            try:
                # Push stats update
                await _push_stats_update(websocket)

                # Wait for client messages or push interval
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=USAGE_LIMIT_WS_PUSH_INTERVAL_SECONDS,
                    )
                    last_activity = time.time()

                    # Handle client messages
                    try:
                        data = json.loads(message)
                        if data.get("type") == "ping":
                            await websocket.send_json({"type": "pong"})
                    except json.JSONDecodeError:
                        pass  # Ignore malformed messages

                except TimeoutError:
                    # No message received — check idle timeout then loop (push next update)
                    if time.time() - last_activity > USAGE_LIMIT_WS_IDLE_TIMEOUT_SECONDS:
                        logger.info(
                            "usage_limit_ws_idle_timeout",
                            user_id=user_id,
                        )
                        await websocket.close(code=4008, reason="Idle timeout")
                        return

            except WebSocketDisconnect:
                logger.info(
                    "usage_limit_ws_client_disconnected",
                    user_id=user_id,
                )
                return

    except Exception as e:
        logger.error(
            "usage_limit_ws_error",
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
        )


async def _push_stats_update(websocket: WebSocket) -> None:
    """Push current usage stats to the connected admin WebSocket.

    Fetches fresh data from the database and sends it as a JSON message.

    Args:
        websocket: Active WebSocket connection.
    """
    try:
        from src.domains.usage_limits.service import UsageLimitService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            service = UsageLimitService(db)
            response = await service.get_admin_list(
                page=1,
                page_size=100,  # Reasonable cap for real-time dashboard
            )

        await websocket.send_json(
            {
                "type": "stats_update",
                "data": [user.model_dump(mode="json") for user in response.users],
                "total": response.total,
            }
        )

    except Exception as e:
        logger.warning(
            "usage_limit_ws_push_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
