"""Reviewed non-secret phone consent values and an injected source write owner."""

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.shared.phone_domains import PHONE_DOMAINS, unknown_phone_domains
from src.domains.users.preference_cas import PreferenceWriteReceipt


class PhonePreferenceValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rich_context_enabled: StrictBool
    disabled_domains: list[StrictStr] = Field(max_length=len(PHONE_DOMAINS))
    call_mode: Literal["direct", "delegated"]

    @field_validator("disabled_domains")
    @classmethod
    def canonical_domains(cls, value: list[str]) -> list[str]:
        if unknown_phone_domains(value):
            raise ValueError("Choose available phone domains")
        return sorted(set(value))


class PhonePreferenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    values: PhonePreferenceValues
    stored_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


PhoneWriteCheck = Callable[[], Awaitable[None]]


class PhonePreferencesGateway(Protocol):
    async def read(self, db: AsyncSession, actor_id: UUID) -> PhonePreferenceSnapshot: ...

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        values: PhonePreferenceValues,
        *,
        expected: PhonePreferenceSnapshot,
        receipt: PreferenceWriteReceipt,
        check: PhoneWriteCheck,
    ) -> None: ...


_gateway: PhonePreferencesGateway | None = None


def configure_phone_preferences(
    gateway: PhonePreferencesGateway | None,
) -> PhonePreferencesGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_phone_preferences() -> PhonePreferencesGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
