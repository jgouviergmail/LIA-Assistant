"""Typed live-reflex values and snapshots; active sessions retain their setup snapshot."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt

EndOfSpeech = Literal["calm", "normal", "lively"]
ResultDelivery = Literal["interrupt", "when_idle"]
LiveReflexName = Literal["interruptions", "end_of_speech", "result_delivery"]


class LiveReflexValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    interruptions: StrictBool
    end_of_speech: EndOfSpeech
    result_delivery: ResultDelivery


class LivePreferenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    values: LiveReflexValues
    provider: str | None = Field(default=None, strict=True, max_length=32)
    stored_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    defaulted_fields: list[LiveReflexName] = Field(default_factory=list, max_length=3)


class LivePreferencesGateway(Protocol):
    async def read(self, db: AsyncSession, actor_id: UUID) -> LivePreferenceSnapshot: ...

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        values: LiveReflexValues,
        *,
        expected: LivePreferenceSnapshot,
        receipt: PreferenceWriteReceipt,
    ) -> None: ...


_gateway: LivePreferencesGateway | None = None


def configure_live_preferences(
    gateway: LivePreferencesGateway | None,
) -> LivePreferencesGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_live_preferences() -> LivePreferencesGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
