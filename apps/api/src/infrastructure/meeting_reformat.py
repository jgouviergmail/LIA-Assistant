"""Original reformat transaction with exact transcript/template/destination consent."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StrictBool, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.core.meeting_reformat import MeetingReformatRequest
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_regeneration import MeetingRegenerationSnapshot


class ConfirmedReformatRequest(MeetingReformatRequest):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MeetingReformatSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: MeetingRegenerationSnapshot
    request: ConfirmedReformatRequest
    destination_id: UUID
    rag_enabled_at_confirmation: StrictBool

    @model_validator(mode="after")
    def target_matches_mode(self) -> MeetingReformatSnapshot:
        same = self.destination_id == self.source.meeting_id
        if same != (self.request.mode == "replace"):
            raise ValueError("Destination must match the original reformat mode")
        return self

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "source": {
                **self.source.public_scope(),
                "replace_entire_current_report": self.request.mode == "replace",
            },
            "request": self.request.model_dump(mode="json"),
            "destination_id": str(self.destination_id),
            "rag_enabled_at_confirmation": self.rag_enabled_at_confirmation,
        }


@dataclass(frozen=True)
class MeetingReformatConfirmation:
    validate: Callable[[MeetingReformatSnapshot], Awaitable[None]]
    check: Callable[[], Awaitable[None]]
    receipt: PreferenceWriteReceipt
    destination_id: UUID


class MeetingReformatGateway(Protocol):
    async def snapshot(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        request: MeetingReformatRequest,
        *,
        destination_id: UUID,
    ) -> MeetingReformatSnapshot: ...
    async def reformat(
        self,
        db: AsyncSession,
        actor_id: UUID,
        selected: MeetingReformatSnapshot,
        confirmation: MeetingReformatConfirmation,
    ) -> None: ...


_gateway: MeetingReformatGateway | None = None


def configure_meeting_reformat(
    gateway: MeetingReformatGateway | None,
) -> MeetingReformatGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_reformat() -> MeetingReformatGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
