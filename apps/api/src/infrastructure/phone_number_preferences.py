"""Non-secret phone-number values; opaque comparison material stays in commands."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt


class PhoneNumberValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    phone_number: str | None
    number_status: Literal["unset", "available", "unreadable"]
    verified: StrictBool
    verified_at: datetime | None


class PhoneNumberSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    values: PhoneNumberValues
    stored_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


PhoneNumberWriteCheck = Callable[[], Awaitable[None]]


class PhoneNumberGateway(Protocol):
    async def read(self, db: AsyncSession, actor_id: UUID) -> PhoneNumberSnapshot: ...

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        number: str | None,
        *,
        expected: PhoneNumberSnapshot,
        receipt: PreferenceWriteReceipt,
        check: PhoneNumberWriteCheck,
    ) -> None: ...


_gateway: PhoneNumberGateway | None = None


def configure_phone_number_preferences(
    gateway: PhoneNumberGateway | None,
) -> PhoneNumberGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_phone_number_preferences() -> PhoneNumberGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
