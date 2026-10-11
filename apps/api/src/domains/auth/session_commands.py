"""Resolve owned display identities; raw Redis session material remains local."""

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.constants import APPLICATION_SESSION_INDEX_MAX_ENTRIES
from src.core.exceptions import (
    AuthorizationError,
    ResourceConflictError,
    raise_not_found_or_unauthorized,
)
from src.domains.auth.session_queries import (
    ListedDeviceSession,
    device_names_by_token_id,
    session_metadata,
)
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_revocation import revoke_selected_sessions
from src.infrastructure.cache.session_store import (
    SessionListingObservation,
    SessionStore,
    UserSession,
)


class SessionRevocationCompletionUnknown(RuntimeError):
    """A sent Redis mutation produced no trustworthy acknowledgement; never replay it."""


async def resolve_owned_session_selection(
    actor_id: UUID, origin: ApplicationOrigin | None, display_id: str
) -> tuple[SessionStore, UserSession, UserSession | None]:
    store, current, sessions = await resolve_owned_session_fleet(actor_id, origin)
    selected = next((item for item in sessions if item.display_id == display_id), None)
    return store, current, selected


async def resolve_owned_session_fleet(
    actor_id: UUID,
    origin: ApplicationOrigin | None,
    *,
    observation: SessionListingObservation | None = None,
) -> tuple[SessionStore, UserSession, tuple[UserSession, ...]]:
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await origin.require_session(actor_id, expected_binding=origin.binding_id)
    store = SessionStore(await get_redis_session())
    sessions = await store.list_user_sessions(
        str(actor_id), max_sessions=APPLICATION_SESSION_INDEX_MAX_ENTRIES, observation=observation
    )
    if len({item.display_id for item in sessions}) != len(sessions):
        raise ValueError("Ambiguous session display identity")
    current = next(
        (
            item
            for item in sessions
            if hmac.compare_digest(
                hashlib.sha256(item.session_id.encode()).hexdigest(), origin.binding_id
            )
        ),
        None,
    )
    if current is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    return store, current, tuple(sessions)


async def read_owned_session_for_revocation(
    db: AsyncSession, actor: User, origin: ApplicationOrigin | None, display_id: str
) -> ListedDeviceSession:
    _, current, selected = await resolve_owned_session_selection(actor.id, origin, display_id)
    if selected is None:
        raise_not_found_or_unauthorized("device session")
    names = await device_names_by_token_id(
        db, actor, token_ids={selected.fcm_token_id} if selected.fcm_token_id else set()
    )
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await origin.require_session(actor.id, expected_binding=origin.binding_id)
    return ListedDeviceSession(
        **session_metadata(selected, names).model_dump(),
        current=selected.session_id == current.session_id,
    )


async def locked_revocation_actor(db: AsyncSession, actor_id: UUID) -> User:
    actor: User | None = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    return actor


async def revoke_owned_device_session(
    db: AsyncSession,
    actor_id: UUID,
    expected: ListedDeviceSession,
    origin: ApplicationOrigin | None,
    receipt: PreferenceWriteReceipt,
    *,
    check: Callable[[], Awaitable[None]],
    approved_until: datetime,
) -> None:
    await locked_revocation_actor(db, actor_id)
    store, current, selected = await resolve_owned_session_selection(actor_id, origin, expected.id)
    if selected is not None and (
        selected.created_at != expected.created_at
        or expected.current != (selected.session_id == current.session_id)
    ):
        raise ResourceConflictError("session", detail={"error_code": "STALE_STATE"})
    await check()
    await locked_revocation_actor(db, actor_id)
    try:
        removed = await revoke_selected_sessions(
            store,
            actor_id,
            (selected,) if selected is not None else (),
            current=current,
            approved_until=approved_until,
        )
    except RedisError:
        raise SessionRevocationCompletionUnknown() from None
    receipt.committed = True
    receipt.no_op = removed == 0
