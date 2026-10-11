"""Original stopped/failed meeting job consent and retry transaction port."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_preferences import MeetingPreferenceState


class MeetingRetrySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    status: StrictStr
    stage: StrictStr | None
    title: StrictStr | None = Field(max_length=200)
    attempts: StrictInt = Field(ge=0)
    audio_files: StrictInt = Field(ge=1)
    audio_bytes_on_disk: StrictInt = Field(gt=0)
    transcript_available: StrictBool
    keep_audio_until: datetime | None
    language: StrictStr
    account_email: StrictStr = Field(max_length=320)
    preferences_at_confirmation: MeetingPreferenceState
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self) -> dict[str, JsonValue]:
        return {**self.model_dump(mode="json", exclude={"source_digest"}), "summary_only": True}


@dataclass(frozen=True)
class MeetingRetryConfirmation:
    validate: Callable[[MeetingRetrySnapshot], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt


class MeetingRetryGateway(Protocol):
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingRetrySnapshot: ...
    async def retry(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingRetryConfirmation,
    ) -> None: ...


_gateway: MeetingRetryGateway | None = None


def configure_meeting_retry(gateway: MeetingRetryGateway | None) -> MeetingRetryGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_retry() -> MeetingRetryGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
