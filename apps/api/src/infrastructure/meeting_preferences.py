"""Portable meeting preference values; the original domain owns validation and writes."""

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX
from src.core.exceptions import AuthorizationError
from src.core.meeting_templates import canonical_template_reference
from src.domains.users.preference_cas import PreferenceWriteReceipt


class MeetingPreferenceValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stt_engine: Literal["auto", "remote", "local"]
    language: str = Field(pattern=r"^(auto|[a-z]{2})$")
    auto_email: StrictBool
    keep_audio_hours: StrictInt = Field(ge=0)
    default_template_ref: str | None = Field(
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=r"^(builtin:[a-z][a-z0-9_]{1,59}|user:[0-9a-fA-F-]{36})$",
    )

    @field_validator("default_template_ref")
    @classmethod
    def canonical_default_reference(cls, value: str | None) -> str | None:
        return canonical_template_reference(value)


class MeetingPreferenceState(MeetingPreferenceValues):
    keep_audio_hours_max: StrictInt = Field(ge=0)


class MeetingPreferenceCompletionUnknown(RuntimeError):
    """A sent commit did not return trustworthy acknowledgment; never automatically replay."""


MeetingPreferenceCheck = Callable[[], Awaitable[None]]


class MeetingPreferenceGateway(Protocol):
    async def read(self, db: AsyncSession, actor_id: UUID) -> MeetingPreferenceState: ...

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        values: MeetingPreferenceValues,
        *,
        expected: MeetingPreferenceState,
        receipt: PreferenceWriteReceipt,
        check: MeetingPreferenceCheck,
    ) -> None: ...


_gateway: MeetingPreferenceGateway | None = None


def configure_meeting_preferences(
    gateway: MeetingPreferenceGateway | None,
) -> MeetingPreferenceGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_preferences() -> MeetingPreferenceGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
