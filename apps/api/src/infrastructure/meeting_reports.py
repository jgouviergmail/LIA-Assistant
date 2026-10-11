"""Strict original-owner report facts and guarded restore port."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt


class MeetingReportState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    status: StrictStr
    stage: StrictStr | None
    location_label: StrictStr | None
    edited_at: datetime | None
    current: dict[str, JsonValue] | None
    current_valid: StrictBool = True
    generated: dict[str, JsonValue]
    matches_generated: StrictBool
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    def public_values(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"source_digest"})


@dataclass(frozen=True)
class ReportWriteConfirmation:
    validate: Callable[[MeetingReportState], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt


class MeetingReportGateway(Protocol):
    async def read_restore(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingReportState: ...
    async def restore(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: ReportWriteConfirmation,
    ) -> None: ...


_gateway: MeetingReportGateway | None = None


def configure_meeting_reports(gateway: MeetingReportGateway | None) -> MeetingReportGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_reports() -> MeetingReportGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
