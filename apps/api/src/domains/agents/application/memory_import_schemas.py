"""Exact consent to import a memories export attached in the chat: the file, and its counts.

The model names the file as the conversation shows it, never by an id it would have to copy: the
server finds it among the files the person attached in this discussion and seals its id. The
memories' words stay private: the proposal seals a digest of the file, compared again at the
confirmation, so a file changed afterwards is never imported on an old consent.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent


class MemoryImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    file_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description=(
            "The attached export's file name exactly as this conversation shows it; omitted, "
            "the export attached most recently in this discussion."
        ),
    )


class MemoryImportSnapshot(BaseModel):
    """What the attached export holds, counted exactly as the import will count it (ADR-185)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    request: MemoryImportInput
    attachment_id: UUID
    file_name: str
    total: int = Field(ge=0)
    new: int = Field(ge=0)
    already_present: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    invalid: int = Field(ge=0)
    file_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"file_digest", "attachment_id", "request"})

    def created_scope(self) -> dict[str, JsonValue]:
        """What the confirmation creates: the memories the account does not hold yet."""
        return {"memories_to_create": self.new}


class MemoryImportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memories_import: MemoryImportSnapshot


class MemoryImportField(StrEnum):
    IMPORT = "memories_import"


def canonical_memory_import(draft: ApplicationActionDraftContent) -> bool:
    selected = MemoryImportPatch.model_validate(draft.intent).memories_import
    return draft.before == {"memories_import": selected.public_scope()} and draft.after == {
        "memories_import": selected.created_scope()
    }
