"""A bounded whole-source synchronization carries an exact current-account selection."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkSelection,
)


class SourceSyncInput(SourceUnlinkInput):
    """Synchronize the named linked source through the existing Source jobs."""


class SourceSyncSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: SourceUnlinkSelection
    max_documents: StrictInt = Field(ge=1)
    max_items: StrictInt = Field(ge=1)
    provider_id: str = Field(min_length=1, max_length=255)
    max_file_bytes: StrictInt = Field(ge=1)
    max_chunks: StrictInt = Field(ge=1)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "space": self.source.space.model_dump(mode="json"),
            "source_id": str(self.source.request.source_id),
            "kind": self.source.request.kind,
            "source_name": self.source.source_name,
            "documents": self.source.documents,
            "max_documents": self.max_documents,
            "max_items": self.max_items,
            "max_file_bytes": self.max_file_bytes,
            "max_chunks": self.max_chunks,
            "sync_status": "syncing" if after else self.source.sync_status,
            "sync_accepted": after,
            "indexing_completed": False,
            "removes_absent_content_after_complete_listing": True,
            "provider_quotas_and_embedding_costs": True,
            "automatic_retry": False,
        }


class SourceSyncPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_to_sync: SourceSyncSelection


class SourceSyncField(StrEnum):
    SOURCE_TO_SYNC = "source_to_sync"


def canonical_source_sync(draft: ApplicationActionDraftContent) -> bool:
    selection = SourceSyncPatch.model_validate(draft.intent).source_to_sync
    return draft.before == {"source_to_sync": selection.public_scope()} and draft.after == {
        "source_to_sync": selection.public_scope(after=True)
    }
