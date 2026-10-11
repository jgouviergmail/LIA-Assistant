"""Typed template port; the original domain supplies its owner at startup."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StrictInt
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.core.meeting_templates import (
    MeetingTemplateCreate,
    MeetingTemplateResponse,
    MeetingTemplateUpdate,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown

TemplateCommitUnknown = CommitCompletionUnknown


class TemplateWriteFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    current: MeetingTemplateResponse | None = None
    default_template_ref: str | None = None
    count: StrictInt | None = None
    maximum: StrictInt | None = None
    values: dict[str, JsonValue]


@dataclass(frozen=True)
class TemplateWriteConfirmation:
    validate: Callable[[TemplateWriteFacts], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt
    created_id: UUID | None = None


class MeetingTemplateGateway(Protocol):
    async def creation_facts(
        self, db: AsyncSession, actor_id: UUID, request: MeetingTemplateCreate, language: str | None
    ) -> TemplateWriteFacts: ...
    async def get(
        self, db: AsyncSession, actor_id: UUID, ref: str, language: str | None
    ) -> MeetingTemplateResponse: ...
    async def default_ref(self, db: AsyncSession, actor_id: UUID) -> str | None: ...
    async def create(
        self,
        db: AsyncSession,
        actor_id: UUID,
        request: MeetingTemplateCreate,
        language: str | None,
        confirmation: TemplateWriteConfirmation,
    ) -> None: ...
    async def update(
        self,
        db: AsyncSession,
        actor_id: UUID,
        ref: str,
        request: MeetingTemplateUpdate,
        confirmation: TemplateWriteConfirmation,
    ) -> None: ...
    async def delete(
        self, db: AsyncSession, actor_id: UUID, ref: str, confirmation: TemplateWriteConfirmation
    ) -> None: ...


_gateway: MeetingTemplateGateway | None = None


def configure_meeting_templates(
    gateway: MeetingTemplateGateway | None,
) -> MeetingTemplateGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_templates() -> MeetingTemplateGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
