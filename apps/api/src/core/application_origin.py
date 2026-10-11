"""Opaque, live transport authority; never a model parameter or persisted proof."""

import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from src.core.application_device_snapshot import RecordingDeviceSnapshot
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.session_freshness import step_up_is_fresh


@dataclass(frozen=True, slots=True)
class ApplicationSessionFacts:
    user_id: UUID
    binding_id: str
    display_id: str
    step_up_at: datetime | None


@dataclass(frozen=True, slots=True)
class ApplicationOrigin:
    user_id: UUID
    binding_id: str
    read_current: Callable[[], Awaitable[ApplicationSessionFacts | None]] = field(
        repr=False, compare=False
    )
    device_id: UUID | None = None
    recording_snapshot: RecordingDeviceSnapshot | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.user_id, UUID)
            or len(self.binding_id) != 64
            or any(char not in "0123456789abcdef" for char in self.binding_id)
            or (self.device_id is not None and not isinstance(self.device_id, UUID))
            or (
                self.recording_snapshot is not None
                and not isinstance(self.recording_snapshot, RecordingDeviceSnapshot)
            )
        ):
            raise ValueError("Application origins require an authenticated UUID and opaque binding")

    async def require_session(
        self,
        actor_id: UUID,
        *,
        expected_binding: str,
        recent_step_up: bool = False,
        window_seconds: int | None = None,
        now: datetime | None = None,
    ) -> ApplicationSessionFacts:
        if actor_id != self.user_id or not hmac.compare_digest(expected_binding, self.binding_id):
            raise AuthorizationError(detail={"error_code": "SESSION_MISMATCH"})
        facts = await self.read_current()
        if (
            facts is None
            or facts.user_id != actor_id
            or not hmac.compare_digest(facts.binding_id, self.binding_id)
        ):
            raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
        if recent_step_up:
            if not step_up_is_fresh(
                facts.step_up_at,
                now or datetime.now(UTC),
                settings.step_up_window_seconds if window_seconds is None else window_seconds,
            ):
                raise AuthorizationError(detail={"error_code": "STEP_UP_REQUIRED"})
        return facts
