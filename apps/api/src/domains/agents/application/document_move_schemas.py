"""Closed movement keeps exact source ids, both spaces, capacity and private SQL proofs."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from src.domains.agents.application.document_delete_schemas import (
    DocumentDeleteInput,
    DocumentDeleteSelection,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget


class DocumentMoveInput(DocumentDeleteInput):
    target_space_id: UUID

    @model_validator(mode="after")
    def distinct_spaces(self) -> Self:
        if self.target_space_id == self.space_id:
            raise ValueError("Choose a different target space")
        return self


class DocumentMoveSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: DocumentMoveInput
    documents: DocumentDeleteSelection = Field(repr=False)
    target: SpaceUpdateTarget
    target_documents: StrictInt = Field(ge=0)
    max_documents: StrictInt = Field(ge=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    target_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "source": self.documents.space.model_dump(mode="json"),
            "target": self.target.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in self.documents.items],
            "chunks": self.documents.chunks,
            "target_documents": self.target_documents
            + (len(self.request.document_ids) if after else 0),
            "max_documents": self.max_documents,
            "missing_files": [
                str(file.document_id) for file in self.documents.files if file.file_digest is None
            ],
            "move_requested": after,
        }


class DocumentMovePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    documents_to_move: DocumentMoveSelection


class DocumentMoveField(StrEnum):
    DOCUMENTS_TO_MOVE = "documents_to_move"


def canonical_document_move(draft: ApplicationActionDraftContent) -> bool:
    selected = DocumentMovePatch.model_validate(draft.intent).documents_to_move
    return draft.before == {"documents_to_move": selected.public_scope()} and draft.after == {
        "documents_to_move": selected.public_scope(after=True)
    }
