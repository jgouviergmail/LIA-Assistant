"""Shared session metadata projections; raw cookies and attestation ids stay internal."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import APPLICATION_SESSION_INDEX_MAX_ENTRIES
from src.domains.auth.schemas import DeviceSessionResponse
from src.domains.notifications.models import UserFCMToken
from src.domains.users.models import User
from src.infrastructure.cache.session_store import (
    SessionListingObservation,
    SessionStore,
    UserSession,
)


class DeviceSessionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    ua_family: str | None
    os_family: str | None
    ip_trunc: str | None
    auth_methods: list[str]
    created_at: datetime
    last_seen_at: datetime | None
    device_name: str | None


class ListedDeviceSession(DeviceSessionMetadata):
    current: bool | None = None


class DeviceSessionsProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessions: list[ListedDeviceSession]
    total: int = Field(ge=0)
    next_cursor: str | None = None
    current_session_known: bool = False
    incomplete: bool = False


def assert_device_session_projection_coverage() -> None:
    if set(DeviceSessionResponse.model_fields) != set(DeviceSessionMetadata.model_fields) | {
        "current"
    }:
        raise AssertionError("New device session fields require native projection review")


assert_device_session_projection_coverage()


async def device_names_by_token_id(
    db: AsyncSession, user: User, *, token_ids: set[str] | None = None
) -> dict[str, str]:
    """Read only display names of owned attestation rows, never their FCM credentials."""
    query = select(UserFCMToken.id, UserFCMToken.device_name).where(
        UserFCMToken.user_id == user.id, UserFCMToken.device_name.is_not(None)
    )
    if token_ids is not None:
        identities = []
        for token_id in token_ids:
            try:
                identities.append(UUID(token_id))
            except ValueError:
                continue
        if not identities:
            return {}
        query = query.where(UserFCMToken.id.in_(identities))
    rows = await db.execute(query)
    return {str(identity): name for identity, name in rows.tuples() if name}


def session_metadata(session: UserSession, device_names: dict[str, str]) -> DeviceSessionMetadata:
    return DeviceSessionMetadata(
        id=session.display_id,
        ua_family=session.ua_family,
        os_family=session.os_family,
        ip_trunc=session.ip_trunc,
        auth_methods=session.auth_methods,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        device_name=device_names.get(session.fcm_token_id) if session.fcm_token_id else None,
    )


async def read_device_sessions(
    db: AsyncSession,
    user: User,
    store: SessionStore,
    *,
    cursor: str | None = None,
    limit: int = 25,
) -> DeviceSessionsProjection:
    observation = SessionListingObservation()
    sessions = await store.list_user_sessions(
        str(user.id), max_sessions=APPLICATION_SESSION_INDEX_MAX_ENTRIES, observation=observation
    )
    identities = [session.display_id for session in sessions]
    if len(set(identities)) != len(identities):
        raise ValueError("Ambiguous session display identity")
    start = identities.index(cursor) + 1 if cursor is not None else 0
    page = sessions[start : start + limit]
    names = await device_names_by_token_id(
        db, user, token_ids={session.fcm_token_id for session in page if session.fcm_token_id}
    )
    return DeviceSessionsProjection(
        sessions=[
            ListedDeviceSession(
                **session_metadata(session, names).model_dump(),
            )
            for session in page
        ],
        total=len(sessions),
        incomplete=observation.incomplete,
        next_cursor=page[-1].display_id if page and start + len(page) < len(sessions) else None,
    )
