"""BFF ticket and bounded first-frame world authentication; no query credentials."""

import asyncio
import secrets
from contextlib import suppress
from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Depends, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError
from starlette.websockets import WebSocketState

from src.core.client_ip import resolve_client_ip
from src.core.config import settings
from src.core.constants import (
    WORLD_SOCKET_CLOSE_INTERNAL,
    WORLD_SOCKET_CLOSE_NORMAL,
    WORLD_SOCKET_CLOSE_POLICY,
    WORLD_SOCKET_CLOSE_TRY_AGAIN,
    WORLD_SOCKET_CLOSE_UNAUTHORIZED,
    WORLD_SOCKET_CLOSE_UPGRADE_REQUIRED,
)
from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BaseAPIException,
    CacheError,
)
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.shared.world_cleanup import install_world_cleanup
from src.domains.users.models import User
from src.domains.world.authority import Identity
from src.domains.world.avatar_router import router as avatar_router
from src.domains.world.collision import SCENE
from src.domains.world.configuration import configured_store
from src.domains.world.environment import router as environment_router
from src.domains.world.experience_router import router as experience_router
from src.domains.world.home_router import router as home_router
from src.domains.world.lifecycle import purge_world_account_best_effort
from src.domains.world.message_router import router as message_router
from src.domains.world.policy import read_policy
from src.domains.world.schemas import (
    AuthFrame,
    ReadyFrame,
    TicketRequest,
    TicketResponse,
)
from src.domains.world.service import WorldService
from src.domains.world.socket_models import (
    ClientProtocolUpgradeRequired,
    require_socket_generation,
)
from src.domains.world.store import WorldIntegrityError, WorldUnavailable
from src.domains.world.tickets import WorldTicket, WorldTickets, cookie_binding
from src.domains.world.transport import (
    origin_allowed,
    receive_text,
    run_connection,
    socket_slot,
)
from src.infrastructure.async_utils import write_through_cancellation
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks.redis_claim import ClaimLost
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

logger = structlog.get_logger(__name__)
install_world_cleanup(purge_world_account_best_effort)
router = APIRouter(prefix="/world", tags=["World"], route_class=PrivateApplicationInputRoute)
router.include_router(home_router)
router.include_router(avatar_router)
router.include_router(message_router)
router.include_router(environment_router)
router.include_router(experience_router)
_ticket_limit = create_user_rate_limiter(
    "world_ticket", max_calls=6, authenticate=get_current_active_session_for_stream
)


@router.post(
    "/ticket",
    response_model=TicketResponse,
    dependencies=[
        *capability_dependencies(PlatformCapability.WORLD),
        Depends(_ticket_limit),
    ],
)
async def create_ticket(
    request: TicketRequest,
    user: User = Depends(get_current_active_session_for_stream),
    lia_session: Annotated[str | None, Cookie()] = None,
) -> TicketResponse:
    """Issue a short-lived one-use cookie-bound ticket after native account and capability checks."""
    if not lia_session:
        raise AuthenticationError(log_level="info")
    try:
        policy = await read_policy(lia_session, str(user.id), {str(user.id)})
    except TimeoutError as exc:
        raise CacheError("world_policy") from exc
    if policy.public_identity is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    redis = await get_redis_cache()
    tickets = WorldTickets(
        redis, namespace=settings.world_namespace, ttl=settings.world_ticket_seconds
    )
    try:
        async with asyncio.timeout(settings.world_authority_timeout):
            token = await tickets.create(
                WorldTicket(
                    account_id=str(user.id),
                    alias=policy.public_identity.name,
                    binding=cookie_binding(lia_session),
                )
            )
    except (RedisError, WorldUnavailable, TimeoutError) as exc:
        raise CacheError("world_ticket") from exc
    return TicketResponse(
        account_id=str(user.id), ticket=token, ttl_seconds=settings.world_ticket_seconds
    )


async def authenticate(
    socket: WebSocket, service: WorldService
) -> tuple[str, Identity, str | None]:
    """Authenticate the first bounded socket frame against the current scene, cookie and one-use ticket.

    Args:
        socket: The accepted World socket.
        service: The scene-scoped World service whose Redis holds the tickets.

    Returns:
        The native cookie, the authenticated World identity and the resume token.

    Raises:
        ClientProtocolUpgradeRequired: The frame declares another socket generation.
        ValueError: The frame is not a valid current authentication frame, or names
            another scene.
        AuthenticationError: The ticket or cookie does not authenticate.
        AuthorizationError: The account cannot publish a World identity.
        RedisError: The ticket store cannot be reached.
        TimeoutError: The authentication deadline expires.
    """
    async with asyncio.timeout(settings.world_auth_timeout):
        text = await receive_text(socket, min(1024, settings.world_frame_bytes))
        require_socket_generation(text)
        frame = AuthFrame.model_validate_json(text)
        if frame.scene != SCENE:
            raise ValueError("world_scene_mismatch")
        cookie = socket.cookies.get(settings.session_cookie_name, "")
        tickets = WorldTickets(
            service.store.redis,
            namespace=settings.world_namespace,
            ttl=settings.world_ticket_seconds,
        )
        ticket = await tickets.consume(frame.ticket, cookie)
        if ticket is None or not cookie:
            raise AuthenticationError(log_level="info")
        policy = await read_policy(cookie, ticket.account_id, {ticket.account_id})
    if policy.public_identity is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    return (
        cookie,
        Identity(
            ticket.account_id,
            policy.public_identity.name,
            policy.language,
            ticket.binding,
            policy.public_identity.appearance,
            policy.public_identity.revision,
        ),
        frame.resume,
    )


async def _serve(socket: WebSocket) -> None:
    """Enforce origin, connection rate and owned socket lease before authoritative World I/O."""
    if not settings.world_enabled:
        raise AuthorizationError(
            detail={"error_code": "CAPABILITY_DISABLED", "capability": "world"}
        )
    # The endpoint never trusts an Origin substring, nor a client-selected channel.
    if not origin_allowed(socket.headers.get("origin"), settings.cors_origins):
        raise AuthorizationError(detail={"error_code": "WORLD_ORIGIN"})
    redis = await get_redis_cache()
    limiter = RedisRateLimiter(redis)
    peer = resolve_client_ip(socket.scope)
    async with asyncio.timeout(settings.world_authority_timeout):
        allowed = await limiter.acquire(
            f"world:runtime:{settings.world_namespace}:connect:{peer}",
            max_calls=30,
            window_seconds=60,
            fail_open=False,
        )
    if not allowed:
        raise WorldUnavailable("connection_rate")
    token = secrets.token_urlsafe(32)
    async with socket_slot(redis, token):
        await socket.accept()
        service = WorldService(configured_store(redis))
        cookie, identity, resume = await authenticate(socket, service)
        connection = await service.enter(identity, resume)
        try:
            async with asyncio.timeout(settings.world_send_timeout):
                await socket.send_text(
                    ReadyFrame(scene=SCENE, resume=connection.controller).model_dump_json()
                )
            await run_connection(socket, cookie, service, connection)
        except BaseAPIException:
            # Explicit revocation releases this controller only. A normal network
            # loss keeps the bounded reconnect grace; stale owners cannot evict successors.
            await service.revoke(connection)
            raise
        finally:
            with suppress(RedisError, WorldUnavailable, TimeoutError):
                cancelled = await write_through_cancellation(
                    lambda: service.disconnect(connection),
                    attempts=2,
                    label="world_presence_disconnect",
                )
                if cancelled:
                    raise asyncio.CancelledError


@router.websocket("/ws")
async def world_socket(socket: WebSocket) -> None:
    """Serve the native World socket and map bounded failures to protocol close codes.

    Another socket generation closes 4426 so the client reloads instead of retrying;
    any other invalid client frame, the frame-rate refusal included, closes 1008; a
    record the server itself produced invalid closes 1011 (the store already logged
    and counted it).

    Args:
        socket: The incoming World socket.
    """
    code = WORLD_SOCKET_CLOSE_NORMAL
    try:
        await _serve(socket)
    except WebSocketDisconnect:
        return
    except ClientProtocolUpgradeRequired:
        code = WORLD_SOCKET_CLOSE_UPGRADE_REQUIRED
    except WorldIntegrityError:
        code = WORLD_SOCKET_CLOSE_INTERNAL
    except RedisError, WorldUnavailable, ClaimLost, TimeoutError:
        code = WORLD_SOCKET_CLOSE_TRY_AGAIN
    except BaseAPIException:
        code = WORLD_SOCKET_CLOSE_UNAUTHORIZED
    except ValueError:
        code = WORLD_SOCKET_CLOSE_POLICY
    except Exception as exc:
        # Never stringify a frame/model validation error: it can contain private text.
        logger.error("world_connection_failed", error_type=type(exc).__name__)
        code = WORLD_SOCKET_CLOSE_INTERNAL
    finally:
        if socket.application_state != WebSocketState.DISCONNECTED:
            with suppress(RuntimeError, WebSocketDisconnect):
                await socket.close(code=code)
