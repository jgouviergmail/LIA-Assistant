"""Typed injected access to saved devices, without notification-domain imports."""

from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError


class NotificationDeviceUnavailable(ValueError):
    """A saved notification device cannot be safely projected."""


class NotificationDeviceValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    device_type: str = Field(strict=True, max_length=20)
    device_name: str | None = Field(default=None, strict=True, max_length=100)
    is_active: StrictBool
    last_used_at: AwareDatetime | None
    created_at: AwareDatetime


class NotificationDeviceSnapshot(NotificationDeviceValue):
    updated_at: AwareDatetime
    token_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class NotificationDevicesProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    devices: list[NotificationDeviceValue]
    total: int
    next_cursor: UUID | None = None


class NotificationDevicesGateway(Protocol):
    async def read(
        self,
        db: AsyncSession,
        actor_id: UUID,
        *,
        device_id: UUID | None,
        after_id: UUID | None,
        limit: int,
    ) -> NotificationDevicesProjection: ...

    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, device_id: UUID
    ) -> NotificationDeviceSnapshot: ...

    async def remove(
        self,
        db: AsyncSession,
        actor_id: UUID,
        device_id: UUID,
        *,
        expected: NotificationDeviceSnapshot,
    ) -> None: ...


_gateway: NotificationDevicesGateway | None = None


def configure_notification_devices(
    gateway: NotificationDevicesGateway | None,
) -> NotificationDevicesGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_notification_devices() -> NotificationDevicesGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
