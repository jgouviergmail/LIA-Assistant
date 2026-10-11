"""Owned current-minutes content witness and original PDF rendering port."""

from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.infrastructure.file_transfer import LocalFileRead


class MeetingPDFSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    title: StrictStr = Field(max_length=200)
    filename: StrictStr
    language: StrictStr
    participants_count: StrictInt = Field(ge=0)
    sections_count: StrictInt = Field(ge=0)
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            **self.model_dump(mode="json", exclude={"source_digest"}),
            "format": "application/pdf",
            "version": "current",
            "entire_report": True,
        }


class MeetingPDFGateway(Protocol):
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID, language: str | None
    ) -> MeetingPDFSnapshot: ...
    async def render(
        self,
        db: AsyncSession,
        actor_id: UUID,
        expected: MeetingPDFSnapshot,
        check: Callable[[], Awaitable[None]],
    ) -> LocalFileRead: ...


_gateway: MeetingPDFGateway | None = None


def configure_meeting_pdf(gateway: MeetingPDFGateway | None) -> MeetingPDFGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_pdf() -> MeetingPDFGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
