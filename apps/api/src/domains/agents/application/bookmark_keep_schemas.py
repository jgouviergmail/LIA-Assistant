"""A short literal consent seals a complete copy privately and publishes quota consequences."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.bookmarks.schemas import BookmarkKeepRequest


class BookmarkKeepInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    message_id: UUID | None = None


assert set(BookmarkKeepInput.model_fields) == set(BookmarkKeepRequest.model_fields)


class ResolvedBookmarkKeepInput(BookmarkKeepInput):
    """The archived id is resolved before any draft is created and never retargeted at execution."""

    message_id: UUID


class BookmarkKeepObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: ResolvedBookmarkKeepInput
    conversation_id: UUID | None
    answered_at: datetime
    answer_preview: str
    request_preview: str | None
    answer_chars: StrictInt
    request_chars: StrictInt | None
    existing_id: UUID | None
    kept_count: StrictInt
    max_per_user: StrictInt
    copy_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        values = self.model_dump(mode="json", exclude={"copy_digest", "kept_count"})
        values["kept_count"] = self.kept_count + int(after and self.existing_id is None)
        values["kept"] = after or self.existing_id is not None
        values["automatic_indexing_may_spend"] = self.existing_id is None
        return values


class BookmarkKeepPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    saved_answer_to_keep: BookmarkKeepObservation


class BookmarkKeepField(StrEnum):
    KEEP = "saved_answer_to_keep"


def canonical_bookmark_keep(draft: ApplicationActionDraftContent) -> bool:
    selected = BookmarkKeepPatch.model_validate(draft.intent).saved_answer_to_keep
    return draft.before == {"saved_answer_to_keep": selected.public_scope()} and draft.after == {
        "saved_answer_to_keep": selected.public_scope(after=True)
    }
