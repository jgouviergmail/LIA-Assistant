"""Exact selected-document removal reuses source ids, metadata and batch limits."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.document_archive_schemas import DocumentArchiveInput
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_delete_schemas import SpaceDeleteDocument
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget


class DocumentDeleteInput(DocumentArchiveInput):
    """Same exact owned-space selection as source document archive requests."""


class DocumentDeleteField(StrEnum):
    DOCUMENTS_TO_DELETE = "documents_to_delete"


class DocumentDeleteFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: UUID
    stored_filename: str = Field(repr=False)
    file_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", repr=False)


class DocumentDeleteSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: DocumentDeleteInput
    space: SpaceUpdateTarget
    items: tuple[SpaceDeleteDocument, ...]
    chunks: StrictInt = Field(ge=0)
    space_documents: StrictInt = Field(ge=1, repr=False)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    files: tuple[DocumentDeleteFile, ...] = Field(repr=False)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "space": self.space.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in self.items],
            "chunks": self.chunks,
            "deletion_requested": after,
        }


class DocumentDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    documents_to_delete: DocumentDeleteSelection


def canonical_document_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = DocumentDeletePatch.model_validate(draft.intent).documents_to_delete
    return draft.before == {"documents_to_delete": selected.public_scope()} and draft.after == {
        "documents_to_delete": selected.public_scope(after=True)
    }
