"""Deletion binds the owned reminder's displayed source configuration."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.core.card_composition import CardCompositionRequest
from src.domains.agents.application.reminder_create_schemas import ReminderRecurrence


class ReminderSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    content: StrictStr
    trigger_at: datetime
    user_timezone: StrictStr
    recurrence: ReminderRecurrence
    created_at: datetime
    configuration_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    card_selection: CardCompositionRequest | None = None


class ReminderDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reminder_id: UUID


class ReminderDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reminder_to_delete: ReminderSnapshot
