"""Source journal management contracts enrich this bounded observer together."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.journals.models import JournalEntryStatus, JournalTheme
from src.domains.journals.schemas import (
    JournalEntryListResponse,
    JournalEntryResponse,
    JournalSettingsResponse,
    JournalThemesResponse,
)


class JournalRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    limit: int = Field(default=5, ge=1, le=50, strict=True)
    after_id: UUID | None = None
    theme: JournalTheme | None = None
    status: JournalEntryStatus | None = None


class JournalProjection(JournalEntryResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")


class JournalsProjection(JournalEntryListResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    settings: JournalSettingsResponse
    themes: JournalThemesResponse
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
    observed_at: datetime
