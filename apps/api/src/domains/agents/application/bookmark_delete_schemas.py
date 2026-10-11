"""Bounded literal consent privately seals the complete saved copy and its projection."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.document_delete_schemas import DocumentDeleteFile
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_delete_schemas import SpaceDeleteDocument


class BookmarkDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    bookmark_id: UUID


class BookmarkDeleteObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: BookmarkDeleteInput
    answered_at: datetime
    answer_preview: str
    request_preview: str | None
    answer_chars: StrictInt
    request_chars: StrictInt | None
    projection: SpaceDeleteDocument | None
    space_id: UUID | None
    chunks: StrictInt = Field(ge=0)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    file: DocumentDeleteFile | None = Field(repr=False)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            **self.model_dump(mode="json", exclude={"state_digest", "file"}),
            "deletion_requested": after,
        }


class BookmarkDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    saved_answer_to_delete: BookmarkDeleteObservation


class BookmarkDeleteField(StrEnum):
    DELETE = "saved_answer_to_delete"


def canonical_bookmark_deletion(draft: ApplicationActionDraftContent) -> bool:
    scope = BookmarkDeletePatch.model_validate(draft.intent).saved_answer_to_delete
    return draft.before == {"saved_answer_to_delete": scope.public_scope()} and draft.after == {
        "saved_answer_to_delete": scope.public_scope(after=True)
    }
