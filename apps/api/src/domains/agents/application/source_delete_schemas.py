"""Exact whole-source removal composes bounded existing document selections."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.document_delete_schemas import DocumentDeleteSelection
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkSelection,
)


class SourceDeleteInput(SourceUnlinkInput):
    """Stop this exact source and remove all documents it currently owns."""


class SourceDeleteSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: SourceUnlinkSelection
    batches: tuple[DocumentDeleteSelection, ...]

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "space": self.source.space.model_dump(mode="json"),
            "source_id": str(self.source.request.source_id),
            "kind": self.source.request.kind,
            "source_name": self.source.source_name,
            "items": [
                item.model_dump(mode="json") for batch in self.batches for item in batch.items
            ],
            "documents": self.source.documents,
            "source_removed": after,
            "documents_deleted": self.source.documents if after else 0,
        }


class SourceDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_to_delete: SourceDeleteSelection


class SourceDeleteField(StrEnum):
    SOURCE_TO_DELETE = "source_to_delete"


def canonical_source_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = SourceDeletePatch.model_validate(draft.intent).source_to_delete
    return draft.before == {"source_to_delete": selected.public_scope()} and draft.after == {
        "source_to_delete": selected.public_scope(after=True)
    }
