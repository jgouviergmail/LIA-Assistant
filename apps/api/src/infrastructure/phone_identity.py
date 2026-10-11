"""Injected phone identity read boundary; keys, OTPs and ciphertext never cross it."""

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError

NativePhoneCallMode = Literal["direct", "delegated"]


class PhoneIdentityData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone_number: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{1,14}$")
    verified: bool
    verified_at: datetime | None = None
    disabled_domains: list[str]
    available_domains: list[str]
    rich_context_enabled: bool
    verification_pending: bool
    call_mode: NativePhoneCallMode
    call_mode_effective: NativePhoneCallMode
    live_available: bool
    live_unavailable_reason: str | None = None


class PhoneIdentityProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: PhoneIdentityData
    number_status: Literal["unset", "available", "unreadable"]


class PhoneIdentityGateway(Protocol):
    async def read(self, db: AsyncSession, actor_id: UUID) -> PhoneIdentityProjection: ...


_gateway: PhoneIdentityGateway | None = None


def configure_phone_identity(gateway: PhoneIdentityGateway | None) -> PhoneIdentityGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_phone_identity() -> PhoneIdentityGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
