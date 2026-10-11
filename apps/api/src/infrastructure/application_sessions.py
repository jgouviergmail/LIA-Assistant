"""Bind the authenticated HTTP cookie through a live, nonserialized session reader."""

import hashlib
import hmac
from dataclasses import replace
from uuid import UUID

from src.core.application_device_identity import parse_application_device_id
from src.core.application_device_snapshot import RecordingDeviceSnapshot
from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
from src.core.constants import APPLICATION_SESSION_INDEX_MAX_ENTRIES
from src.core.exceptions import AuthorizationError
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore


async def require_live_application_binding(actor_id: UUID, binding_id: str) -> None:
    """Observe actual stored sessions for a callback; never construct browser authority."""
    store = SessionStore(await get_redis_session())
    sessions = await store.list_user_sessions(
        str(actor_id), max_sessions=APPLICATION_SESSION_INDEX_MAX_ENTRIES
    )
    if not any(
        hmac.compare_digest(hashlib.sha256(item.session_id.encode()).hexdigest(), binding_id)
        for item in sessions
    ):
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})


def bind_browser_recording_session(
    actor_id: UUID,
    session_cookie: str | None,
    *,
    device_id: str | None,
    recording_snapshot: RecordingDeviceSnapshot | None,
) -> ApplicationOrigin | None:
    origin = bind_browser_session(actor_id, session_cookie, device_id=device_id)
    return replace(origin, recording_snapshot=recording_snapshot) if origin is not None else None


def bind_browser_session(
    actor_id: UUID, session_cookie: str | None, *, device_id: str | None = None
) -> ApplicationOrigin | None:
    if not session_cookie:
        return None
    binding = hashlib.sha256(session_cookie.encode("utf-8")).hexdigest()

    async def read_current() -> ApplicationSessionFacts | None:
        store = SessionStore(await get_redis_session())
        session = await store.get_session(session_cookie)
        if session is None or session.user_id != str(actor_id):
            return None
        return ApplicationSessionFacts(
            user_id=actor_id,
            binding_id=binding,
            display_id=session.display_id,
            step_up_at=session.step_up_at,
        )

    return ApplicationOrigin(
        user_id=actor_id,
        binding_id=binding,
        read_current=read_current,
        device_id=parse_application_device_id(device_id),
    )
