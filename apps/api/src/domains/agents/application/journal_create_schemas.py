"""Manual creation inherits source fields, with bounded hints for provider input."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.domains.journals.schemas import JournalEntryCreate


class JournalCreateConfiguration(JournalEntryCreate):
    model_config = ConfigDict(frozen=True, extra="forbid")
    search_hints: (
        list[Annotated[str, StringConstraints(min_length=1, max_length=100, strict=True)]] | None
    ) = Field(default=None, max_length=5)


class JournalCreationValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    configuration: JournalCreateConfiguration


class JournalCreatePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    journal_entry_to_create: JournalCreationValues


class JournalCreationField(StrEnum):
    ENTRY = "journal_entry_to_create"


if set(JournalEntryCreate.model_fields) != {"theme", "title", "content", "mood", "search_hints"}:
    raise AssertionError(
        "New manual journal fields require reviewed source effects and confirmation"
    )
