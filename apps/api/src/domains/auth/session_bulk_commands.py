"""Revoke a frozen fleet through the shared atomic Redis owner, after live step-up."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.auth.session_bulk_schemas import OtherDeviceSessionsSelection
from src.domains.auth.session_commands import (
    SessionRevocationCompletionUnknown,
    locked_revocation_actor,
    resolve_owned_session_fleet,
)
from src.domains.auth.session_queries import (
    ListedDeviceSession,
    device_names_by_token_id,
    session_metadata,
)
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.cache.session_revocation import revoke_selected_sessions
from src.infrastructure.cache.session_store import (
    SessionListingObservation,
    SessionStore,
    UserSession,
)


async def _complete_fleet(
    actor_id: UUID, origin: ApplicationOrigin | None
) -> tuple[SessionStore, UserSession, tuple[UserSession, ...]]:
    observation = SessionListingObservation()
    fleet = await resolve_owned_session_fleet(actor_id, origin, observation=observation)
    if observation.incomplete:
        raise ResourceConflictError("sessions", detail={"error_code": "STALE_STATE"})
    return fleet


async def read_owned_other_device_sessions(
    db: AsyncSession, actor: User, origin: ApplicationOrigin | None
) -> OtherDeviceSessionsSelection:
    _, current, sessions = await _complete_fleet(actor.id, origin)
    others = [item for item in sessions if item.session_id != current.session_id]
    names = await device_names_by_token_id(
        db, actor, token_ids={item.fcm_token_id for item in others if item.fcm_token_id}
    )
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await origin.require_session(actor.id, expected_binding=origin.binding_id)
    return OtherDeviceSessionsSelection(
        current_display_id=current.display_id,
        sessions=tuple(
            ListedDeviceSession(**session_metadata(item, names).model_dump(), current=False)
            for item in others
        ),
    )


async def revoke_owned_other_device_sessions(
    db: AsyncSession,
    actor_id: UUID,
    expected: OtherDeviceSessionsSelection,
    origin: ApplicationOrigin | None,
    receipt: PreferenceWriteReceipt,
    *,
    check: Callable[[], Awaitable[None]],
    approved_until: datetime,
) -> int:
    expected = OtherDeviceSessionsSelection.model_validate(expected)
    await locked_revocation_actor(db, actor_id)
    store, current, sessions = await _complete_fleet(actor_id, origin)
    if expected.current_display_id != current.display_id:
        raise AuthorizationError(detail={"error_code": "SESSION_MISMATCH"})
    by_id = {item.display_id: item for item in sessions}
    selected = []
    for approved in expected.sessions:
        saved = by_id.get(approved.id)
        if saved is None:
            continue
        if saved.created_at != approved.created_at or saved.session_id == current.session_id:
            raise ResourceConflictError("sessions", detail={"error_code": "STALE_STATE"})
        selected.append(saved)
    await check()
    await locked_revocation_actor(db, actor_id)
    try:
        removed = await revoke_selected_sessions(
            store,
            actor_id,
            tuple(selected),
            current=current,
            require_fresh_step_up=True,
            approved_until=approved_until,
        )
    except RedisError:
        raise SessionRevocationCompletionUnknown() from None
    receipt.committed = True
    receipt.no_op = removed == 0
    return removed
