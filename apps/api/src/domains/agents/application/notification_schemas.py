"""Saved notification device identity is separate from browser permission and push credentials."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.infrastructure.notification_devices import NotificationDeviceSnapshot


class NotificationDeviceField(str, Enum):
    DEVICE = "notification_device_to_remove"


class NotificationDevicesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: UUID | None = None
    after_id: UUID | None = None
    limit: StrictInt = Field(default=25, ge=1, le=50)


class NotificationDeviceRemoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: UUID


class NotificationDeviceRemovePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    notification_device_to_remove: NotificationDeviceSnapshot
