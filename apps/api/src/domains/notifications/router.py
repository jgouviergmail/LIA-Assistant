"""
API router for notifications domain.

Endpoints for FCM token management and SSE notifications.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import HTTP_TIMEOUT_SSE_POLLING
from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_invalid_input,
    raise_push_token_not_found,
    raise_test_endpoint_disabled,
)
from src.core.session_dependencies import get_current_active_session, get_current_superuser_session
from src.domains.auth.models import User
from src.domains.notifications.broadcast_service import BroadcastService
from src.domains.notifications.schemas import (
    BroadcastMessageRequest,
    BroadcastMessageResponse,
    TokenInfo,
    TokenRegisterRequest,
    TokenRegisterResponse,
    TokenUnregisterRequest,
    TokenUnregisterResponse,
    UnreadBroadcastsResponse,
    UserTokensResponse,
)
from src.domains.notifications.service import FCMNotificationService
from src.domains.users.repository import UserRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# =============================================================================
# FCM Token Management
# =============================================================================


@router.post(
    "/register-token",
    response_model=TokenRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register FCM token",
    description="Register a Firebase Cloud Messaging token for push notifications.",
)
async def register_fcm_token(
    request: TokenRegisterRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TokenRegisterResponse:
    """
    Register an FCM token for the current user.

    This endpoint should be called:
    - When the user grants notification permission
    - When the app starts (token may have changed)
    - When the user logs in on a new device
    """
    service = FCMNotificationService(db)

    token = await service.register_token(
        user_id=current_user.id,
        token=request.token,
        device_type=request.device_type,
        device_name=request.device_name,
    )

    await db.commit()

    return TokenRegisterResponse(
        id=token.id,
        device_type=token.device_type,
        device_name=token.device_name,
        created_at=token.created_at,
    )


@router.post(
    "/unregister-token",
    response_model=TokenUnregisterResponse,
    summary="Unregister FCM token",
    description="Remove an FCM token (e.g., on logout).",
)
async def unregister_fcm_token(
    request: TokenUnregisterRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TokenUnregisterResponse:
    """
    Unregister an FCM token.

    Should be called when:
    - User logs out
    - User disables notifications
    """
    service = FCMNotificationService(db)

    success = await service.unregister_token(request.token)

    await db.commit()

    if success:
        return TokenUnregisterResponse(
            success=True,
            message="Token unregistered successfully",
        )
    else:
        return TokenUnregisterResponse(
            success=False,
            message="Token not found",
        )


@router.get(
    "/tokens",
    response_model=UserTokensResponse,
    summary="List user tokens",
    description="List all registered FCM tokens for the current user.",
)
async def list_user_tokens(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserTokensResponse:
    """
    List all FCM tokens for the current user.

    Useful for debugging and managing notification devices.
    """
    service = FCMNotificationService(db)

    tokens = await service.get_user_tokens(current_user.id)

    token_infos = [
        TokenInfo(
            id=t.id,
            device_type=t.device_type,
            device_name=t.device_name,
            is_active=t.is_active,
            last_used_at=t.last_used_at,
            created_at=t.created_at,
        )
        for t in tokens
    ]

    return UserTokensResponse(
        tokens=token_infos,
        total=len(token_infos),
    )


@router.delete(
    "/tokens/{token_id}",
    response_model=TokenUnregisterResponse,
    summary="Delete token by ID",
    description="Remove an FCM token by its ID.",
)
async def delete_token_by_id(
    token_id: str,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TokenUnregisterResponse:
    """
    Delete an FCM token by its ID.

    The token must belong to the current user.
    """
    from uuid import UUID

    service = FCMNotificationService(db)

    try:
        token_uuid = UUID(token_id)
    except ValueError:
        raise_invalid_input("Invalid token ID format", token_id=token_id)

    success = await service.delete_token_by_id(
        token_id=token_uuid,
        user_id=current_user.id,
    )

    await db.commit()

    if success:
        return TokenUnregisterResponse(
            success=True,
            message="Token deleted successfully",
        )
    else:
        raise_push_token_not_found(current_user.id)


# =============================================================================
# SSE Notifications Stream
# =============================================================================


@router.get(
    "/stream",
    summary="SSE notifications stream",
    description="Server-Sent Events stream for real-time notifications.",
)
async def stream_notifications(
    current_user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """
    SSE endpoint for real-time notifications.

    Subscribes to Redis Pub/Sub channel for the user and streams
    notifications as Server-Sent Events.

    Use this endpoint when the user has the app open to receive
    real-time updates (like reminders).

    SSE Connection Tracking:
        - Sets Redis key when connection established
        - Refreshes TTL on each keepalive
        - Deletes key when connection closes
        - Used by OAuth health check to avoid duplicate push notifications
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from Redis Pub/Sub."""
        from src.core.config import settings
        from src.core.constants import SSE_CONNECTION_KEY_PREFIX
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if redis is None:
            yield "event: error\ndata: Redis not available\n\n"
            return

        channel = f"user_notifications:{current_user.id}"
        sse_key = f"{SSE_CONNECTION_KEY_PREFIX}:{current_user.id}"
        sse_ttl = settings.sse_connection_ttl_seconds
        pubsub = redis.pubsub()

        try:
            await pubsub.subscribe(channel)

            # Track SSE connection in Redis for OAuth health check deduplication
            await redis.setex(sse_key, sse_ttl, "1")

            logger.info(
                "sse_client_connected",
                user_id=str(current_user.id),
                channel=channel,
                sse_ttl=sse_ttl,
            )

            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            while True:
                try:
                    # IMPORTANT: timeout must be passed to get_message() directly
                    # Without it, get_message() returns immediately with None (busy-wait!)
                    # With timeout=30.0, it blocks for up to 30s waiting for a message
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=HTTP_TIMEOUT_SSE_POLLING,
                    )

                    if message is None:
                        # Timeout reached, no message - send keepalive and refresh SSE tracking
                        await redis.expire(sse_key, sse_ttl)
                        yield ": keepalive\n\n"
                    elif message["type"] == "message":
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")

                        yield f"event: notification\ndata: {data}\n\n"

                except Exception as e:
                    logger.warning(
                        "sse_get_message_error",
                        user_id=str(current_user.id),
                        error=str(e),
                    )
                    # Small delay before retry to avoid tight loop on errors
                    await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            logger.info(
                "sse_client_disconnected",
                user_id=str(current_user.id),
            )
        except Exception as e:
            logger.error(
                "sse_stream_error",
                user_id=str(current_user.id),
                error=str(e),
            )
            yield f"event: error\ndata: {json.dumps({'error': 'An unexpected error occurred'})}\n\n"
        finally:
            # Clean up SSE tracking key on disconnect
            try:
                await redis.delete(sse_key)
            except Exception:
                pass  # Best effort cleanup
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# =============================================================================
# Admin Broadcast Messages
# =============================================================================


@router.post(
    "/admin/broadcast",
    response_model=BroadcastMessageResponse,
    summary="Send broadcast to users (Admin)",
    description="Send a broadcast message to all active users or selected users via SSE and FCM.",
)
async def send_broadcast(
    request: BroadcastMessageRequest,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> BroadcastMessageResponse:
    """
    Send a broadcast message to users.

    Admin-only endpoint. Sends:
    - SSE notification to users with active connections
    - FCM push notification to offline users

    If user_ids is provided, sends only to those users.
    Otherwise, sends to all active users.

    The message is persisted first (Archive-First pattern), ensuring
    all users will eventually see it even if they were offline.
    """
    service = BroadcastService(db)

    result = await service.send_broadcast(
        message=request.message,
        admin_user_id=current_user.id,
        expires_in_days=request.expires_in_days,
        user_ids=request.user_ids,
    )

    # Create audit log
    is_targeted = request.user_ids is not None and len(request.user_ids) > 0
    user_repo = UserRepository(db)
    await user_repo.create_audit_log(
        admin_user_id=current_user.id,
        action="admin_broadcast_sent",
        resource_type="broadcast",
        resource_id=result.broadcast_id,
        details={
            "message_preview": request.message[:100],
            "total_users": result.total_users,
            "fcm_sent": result.fcm_sent,
            "fcm_failed": result.fcm_failed,
            "expires_in_days": request.expires_in_days,
            "is_targeted": is_targeted,
            "target_user_ids": (
                [str(uid) for uid in request.user_ids] if is_targeted and request.user_ids else None
            ),
        },
    )
    await db.commit()

    return BroadcastMessageResponse(
        success=result.success,
        broadcast_id=result.broadcast_id,
        total_users=result.total_users,
        fcm_sent=result.fcm_sent,
        fcm_failed=result.fcm_failed,
    )


@router.get(
    "/broadcasts/unread",
    response_model=UnreadBroadcastsResponse,
    summary="Get unread broadcasts",
    description="Get recent unread broadcast messages for the current user.",
)
async def get_unread_broadcasts(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UnreadBroadcastsResponse:
    """
    Get unread broadcasts for the current user.

    Called by the frontend:
    - At login to show any broadcasts missed while offline
    - On visibility change (app comes to foreground)

    Only considers the N most recent eligible broadcasts (non-expired,
    created after the user's signup). From those, returns the ones the user
    hasn't marked as read yet, translated to their preferred language.
    This prevents new users from seeing old broadcasts and limits notification
    volume for existing users.
    """
    service = BroadcastService(db)
    broadcasts = await service.get_unread_broadcasts(
        user_id=current_user.id,
        user_language=current_user.language,  # type: ignore[arg-type]
        user_created_at=current_user.created_at,
    )

    return UnreadBroadcastsResponse(
        broadcasts=broadcasts,
        total=len(broadcasts),
    )


@router.post(
    "/broadcasts/{broadcast_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark broadcast as read",
    description="Mark a broadcast message as read for the current user.",
)
async def mark_broadcast_read(
    broadcast_id: str,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Mark a broadcast as read for the current user.

    Called when user dismisses the broadcast modal.
    Idempotent: can be called multiple times safely.
    """
    from uuid import UUID

    try:
        broadcast_uuid = UUID(broadcast_id)
    except ValueError:
        raise_invalid_input("Invalid broadcast ID format", broadcast_id=broadcast_id)

    service = BroadcastService(db)
    await service.mark_broadcast_read(current_user.id, broadcast_uuid)


# =============================================================================
# Test Endpoint (Development Only)
# =============================================================================


@router.post(
    "/test",
    summary="Test notification",
    description="Send a test notification (development only).",
    include_in_schema=False,  # Hidden from OpenAPI docs
)
async def send_test_notification(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Send a test notification to the current user.

    Only available in development mode.
    """
    from src.core.config import settings

    if settings.is_production:
        raise_test_endpoint_disabled()

    service = FCMNotificationService(db)

    result = await service.send_to_user(
        user_id=current_user.id,
        title="Test Notification",
        body="This is a test notification from LIA!",
        data={"type": "test"},
    )

    return {
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "results": [
            {
                "success": r.success,
                "message_id": r.message_id,
                "error": r.error,
            }
            for r in result.results
        ],
    }
