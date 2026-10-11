"""Only the source supplies private complete journal removal snapshots."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.journals.removal_snapshot import JournalRemovalSnapshot


class JournalDeleteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    # Required: an explicit null requests all owned entries, never an accidental default.
    entry_id: UUID | None


class JournalDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    journal_entries_to_delete: JournalRemovalSnapshot


class JournalRemovalField(StrEnum):
    ENTRIES = "journal_entries_to_delete"
