"""Owned minutes delivery facts and original SMTP sender port."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt


class MeetingEmailSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    title: StrictStr = Field(max_length=200)
    recipient: StrictStr = Field(max_length=320)
    sender: StrictStr = Field(max_length=320)
    subject: StrictStr = Field(max_length=512)
    language: StrictStr
    participants_count: StrictInt = Field(ge=0)
    sections_count: StrictInt = Field(ge=0)
    previous_sent_at: datetime | None
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            **self.model_dump(mode="json", exclude={"source_digest"}),
            "version": "current",
            "entire_report": True,
            "summary_only": True,
        }


@dataclass(frozen=True)
class MeetingEmailConfirmation:
    validate: Callable[[MeetingEmailSnapshot], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt


class MeetingEmailCompletionUnknown(RuntimeError):
    """An attempted SMTP effect or metadata acknowledgment cannot safely be retried."""


class MeetingEmailGateway(Protocol):
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingEmailSnapshot: ...
    async def send(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingEmailConfirmation,
    ) -> None: ...


_gateway: MeetingEmailGateway | None = None


def configure_meeting_email(gateway: MeetingEmailGateway | None) -> MeetingEmailGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_email() -> MeetingEmailGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
