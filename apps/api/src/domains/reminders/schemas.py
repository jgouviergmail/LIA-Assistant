"""
Reminder domain Pydantic schemas.

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.reminders.models import ReminderStatus


class ReminderCreate(BaseModel):
    """Schema for creating a new reminder."""

    content: str = Field(..., description="What to remind (interpreted)")
    original_message: str = Field(..., description="Original user message")
    trigger_at: datetime = Field(..., description="When to trigger (local time)")


class ReminderResponse(BaseModel):
    """Schema for reminder response."""

    id: UUID
    user_id: UUID
    content: str
    original_message: str
    trigger_at: datetime
    user_timezone: str
    status: ReminderStatus
    retry_count: int
    notification_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReminderListResponse(BaseModel):
    """Schema for listing reminders."""

    reminders: list[ReminderResponse]
    total: int


class ReminderStatusUpdate(BaseModel):
    """Schema for updating reminder status."""

    status: ReminderStatus
    notification_error: str | None = None
