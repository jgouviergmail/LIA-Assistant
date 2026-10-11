"""Strict sparse-change facts exposed by the original minutes writer."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.core.meeting_reports import MeetingPatchRequest
from src.domains.users.preference_cas import PreferenceWriteReceipt


class ReportPatchState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    status: StrictStr
    stage: StrictStr | None
    edited_at: datetime | None
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]


@dataclass(frozen=True)
class ReportPatchConfirmation:
    validate: Callable[[ReportPatchState], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt


class MeetingReportUpdateGateway(Protocol):
    async def read_update(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        changes: MeetingPatchRequest,
        language: str | None,
    ) -> ReportPatchState: ...
    async def update(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        changes: MeetingPatchRequest,
        language: str | None,
        confirmation: ReportPatchConfirmation,
    ) -> None: ...


_gateway: MeetingReportUpdateGateway | None = None


def configure_meeting_report_updates(
    gateway: MeetingReportUpdateGateway | None,
) -> MeetingReportUpdateGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_report_updates() -> MeetingReportUpdateGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
