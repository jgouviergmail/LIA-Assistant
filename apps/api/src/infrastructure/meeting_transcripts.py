"""Typed original-owner transcript purge facts and confirmation callbacks."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt


class MeetingTranscriptState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    title: StrictStr | None
    status: StrictStr
    stage: StrictStr | None
    has_transcript: StrictBool
    deleted_at: datetime | None
    transcript_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    def public_values(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"transcript_digest"})


@dataclass(frozen=True)
class TranscriptWriteConfirmation:
    validate: Callable[[MeetingTranscriptState], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt


class MeetingTranscriptGateway(Protocol):
    async def read(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingTranscriptState: ...
    async def delete(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: TranscriptWriteConfirmation,
    ) -> None: ...


_gateway: MeetingTranscriptGateway | None = None


def configure_meeting_transcripts(
    gateway: MeetingTranscriptGateway | None,
) -> MeetingTranscriptGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_transcripts() -> MeetingTranscriptGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
