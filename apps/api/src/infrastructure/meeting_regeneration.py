"""Owned transcript/current-template witness and original rebuild transaction port."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX
from src.core.exceptions import AuthorizationError
from src.core.meeting_templates import MAX_TEMPLATE_SECTIONS, TemplateSection
from src.domains.users.preference_cas import PreferenceWriteReceipt


class ConfirmedTemplateSection(TemplateSection):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RegenerationTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: StrictStr = Field(max_length=MEETINGS_TEMPLATE_REF_MAX)
    name: StrictStr = Field(max_length=120)
    sections: tuple[ConfirmedTemplateSection, ...] = Field(
        min_length=1, max_length=MAX_TEMPLATE_SECTIONS
    )


class MeetingRegenerationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    status: StrictStr
    stage: StrictStr | None
    current_title: StrictStr | None = Field(max_length=200)
    current_valid: StrictBool
    current_participants_count: StrictInt | None = Field(ge=0)
    current_sections_count: StrictInt | None = Field(ge=0)
    transcript_turns: StrictInt = Field(ge=0)
    language: StrictStr
    template_definition_at_confirmation: RegenerationTemplate
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            **self.model_dump(mode="json", exclude={"source_digest"}),
            "summary_only": True,
            "replace_entire_current_report": True,
        }


@dataclass(frozen=True)
class MeetingRegenerationConfirmation:
    validate: Callable[[MeetingRegenerationSnapshot], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt


class MeetingRegenerationGateway(Protocol):
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingRegenerationSnapshot: ...
    async def regenerate(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingRegenerationConfirmation,
    ) -> None: ...


_gateway: MeetingRegenerationGateway | None = None


def configure_meeting_regeneration(
    gateway: MeetingRegenerationGateway | None,
) -> MeetingRegenerationGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_regeneration() -> MeetingRegenerationGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
