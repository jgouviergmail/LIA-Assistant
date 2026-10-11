"""Exact whole-meeting deletion port without exposing report, transcript or file paths."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt


class MeetingDeletionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    status: StrictStr
    stage: StrictStr | None
    title: StrictStr | None = Field(max_length=200)
    current_valid: StrictBool
    current_sections_count: StrictInt | None = Field(ge=0)
    generated_report_present: StrictBool
    transcript_present: StrictBool
    audio_files: StrictInt = Field(ge=0)
    audio_bytes_on_disk: StrictInt = Field(ge=0)
    projection_id: UUID | None
    projection_present: StrictBool
    derived_minutes_kept: StrictInt = Field(ge=0)
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            **self.model_dump(mode="json", exclude={"source_digest"}),
            "summary_only": True,
            "delete_entire_meeting": True,
            "derived_minutes_deleted": False,
        }


@dataclass(frozen=True)
class MeetingDeletionConfirmation:
    validate: Callable[[MeetingDeletionSnapshot], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt


class MeetingDeletionGateway(Protocol):
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingDeletionSnapshot: ...
    async def delete(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingDeletionConfirmation,
    ) -> None: ...


_gateway: MeetingDeletionGateway | None = None


def configure_meeting_deletions(
    gateway: MeetingDeletionGateway | None,
) -> MeetingDeletionGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_deletions() -> MeetingDeletionGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
