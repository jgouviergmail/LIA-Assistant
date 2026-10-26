"""Native authenticated private HTTP lanes, independent from shared snapshots."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Depends
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.constants import REDIS_KEY_WORLD_MESSAGE_PREFIX
from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CacheError,
    DatabaseError,
    RateLimitError,
    ResourceConflictError,
)
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.world.message_attempts import (
    QUEUE_SECONDS,
    AttemptBusy,
    AttemptConflict,
)
from src.domains.world.messages import (
    MailboxScope,
    MessageRequest,
    MessageStatusRequest,
    RetranslateRequest,
)
from src.domains.world.messaging import MailboxView, MessageAccepted, WorldMessaging
from src.domains.world.peer_views import PeerPage, PeerPageRequest, read_peer_page
from src.domains.world.public_models import PublicMessageRequest
from src.domains.world.store import WorldStore, WorldUnavailable
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

logger = structlog.get_logger(__name__)
router = APIRouter(
    prefix="/messages",
    route_class=PrivateApplicationInputRoute,
    dependencies=capability_dependencies(PlatformCapability.WORLD),
)


@asynccontextmanager
async def message_errors() -> AsyncIterator[None]:
    """Map bounded authority, validation and contention failures to private API errors."""
    try:
        yield
    except AttemptBusy:
        raise RateLimitError(
            1,
            QUEUE_SECONDS,
            1,
            detail={"error_code": "WORLD_TRANSLATION_BUSY"},
            headers={"Retry-After": "1"},
        ) from None
    except AttemptConflict:
        raise ResourceConflictError(
            "world_message", detail={"error_code": "WORLD_MESSAGE_CONFLICT"}
        ) from None
    except (RedisError, WorldUnavailable, TimeoutError) as exc:
        logger.warning("world_message_cache_unavailable", error_type=type(exc).__name__)
        raise CacheError("world_messages") from None
    except SQLAlchemyError as exc:
        logger.warning("world_message_database_unavailable", error_type=type(exc).__name__)
        raise DatabaseError("world_messages") from None
    except ValueError:
        raise AuthorizationError(detail={"error_code": "WORLD_MESSAGE_UNAVAILABLE"}) from None


async def get_messaging() -> WorldMessaging:
    """Assemble native private/public messaging on the configured scene-scoped Redis store."""
    return WorldMessaging(
        WorldStore(
            await get_redis_cache(),
            namespace=settings.world_namespace,
            ttl=settings.world_state_seconds,
            timeout=settings.world_authority_timeout,
        )
    )


async def _limit(user: User, *, action: str, maximum: int) -> None:
    """Acquire a fail-closed, account-scoped HTTP message rate limit."""
    async with message_errors():
        redis = await get_redis_cache()
        async with asyncio.timeout(settings.world_authority_timeout):
            allowed = await RedisRateLimiter(redis).acquire(
                f"{REDIS_KEY_WORLD_MESSAGE_PREFIX}rate:{action}:{user.id}",
                max_calls=maximum,
                window_seconds=60,
                fail_open=False,
            )
        if not allowed:
            raise RateLimitError(maximum, 60, 60, headers={"Retry-After": "60"})


async def write_limit(
    user: User = Depends(get_current_active_session_for_stream),
) -> None:
    """Enforce the authenticated account's bounded message write rate."""
    await _limit(user, action="write", maximum=6)


async def read_limit(
    user: User = Depends(get_current_active_session_for_stream),
) -> None:
    """Enforce the authenticated account's bounded mailbox read rate."""
    await _limit(user, action="read", maximum=60)


def required_cookie(cookie: str | None) -> str:
    """Require the native HttpOnly session cookie before entering the message service."""
    if not cookie:
        raise AuthenticationError(log_level="info")
    return cookie


@router.post(
    "/send",
    response_model=MessageAccepted,
    status_code=202,
    dependencies=[Depends(write_limit)],
)
async def send_message(
    payload: MessageRequest,
    user: User = Depends(get_current_active_session_for_stream),
    lia_session: Annotated[str | None, Cookie()] = None,
    service: WorldMessaging = Depends(get_messaging),
) -> MessageAccepted:
    """Accept an explicit private intent and dispatch only its newly owned asynchronous job."""
    async with message_errors():
        accepted = await service.send(required_cookie(lia_session), str(user.id), payload)
    if accepted.job is not None:
        safe_fire_and_forget(accepted.job, name="world_translation")
    return accepted.ack


@router.post(
    "/public",
    response_model=MessageAccepted,
    status_code=202,
    dependencies=[Depends(write_limit)],
)
async def send_public_message(
    payload: PublicMessageRequest,
    user: User = Depends(get_current_active_session_for_stream),
    lia_session: Annotated[str | None, Cookie()] = None,
    service: WorldMessaging = Depends(get_messaging),
) -> MessageAccepted:
    """Accept an explicit frozen-audience intent and dispatch only its newly owned batch job."""
    async with message_errors():
        accepted = await service.public.send(required_cookie(lia_session), str(user.id), payload)
    if accepted.job is not None:
        safe_fire_and_forget(accepted.job, name="world_public_translation")
    return accepted.ack


@router.post("/read", response_model=MailboxView, dependencies=[Depends(read_limit)])
async def read_messages(
    payload: MailboxScope,
    user: User = Depends(get_current_active_session_for_stream),
    lia_session: Annotated[str | None, Cookie()] = None,
    service: WorldMessaging = Depends(get_messaging),
) -> MailboxView:
    """Return the live account's bounded mailbox and own-language public projections."""
    async with message_errors():
        return await service.read(required_cookie(lia_session), str(user.id), payload)


@router.post("/status", response_model=MessageAccepted, dependencies=[Depends(read_limit)])
async def message_status(
    payload: MessageStatusRequest,
    user: User = Depends(get_current_active_session_for_stream),
    lia_session: Annotated[str | None, Cookie()] = None,
    service: WorldMessaging = Depends(get_messaging),
) -> MessageAccepted:
    """Read a durable owned outcome without replaying an uncertain send."""
    async with message_errors():
        return await service.status(required_cookie(lia_session), str(user.id), payload)


@router.post(
    "/translate",
    response_model=MessageAccepted,
    status_code=202,
    dependencies=[Depends(write_limit)],
)
async def translate_existing(
    payload: RetranslateRequest,
    user: User = Depends(get_current_active_session_for_stream),
    lia_session: Annotated[str | None, Cookie()] = None,
    service: WorldMessaging = Depends(get_messaging),
) -> MessageAccepted:
    """Accept an explicitly consented retranslation without resending a message."""
    async with message_errors():
        accepted = await service.retranslate(required_cookie(lia_session), str(user.id), payload)
    if accepted.job is not None:
        safe_fire_and_forget(accepted.job, name="world_translation")
    return accepted.ack


@router.post("/peers", response_model=PeerPage, dependencies=[Depends(read_limit)])
async def peer_proxies(
    payload: PeerPageRequest,
    user: User = Depends(get_current_active_session_for_stream),
    lia_session: Annotated[str | None, Cookie()] = None,
    service: WorldMessaging = Depends(get_messaging),
) -> PeerPage:
    """Read authorized neutral peer-directory projections for the current controller."""
    async with message_errors():
        return await read_peer_page(
            service.access, required_cookie(lia_session), str(user.id), payload
        )
