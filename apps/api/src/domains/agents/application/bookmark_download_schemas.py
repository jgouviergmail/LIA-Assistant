"""A complete copied-answer download publishes metadata only and seals all Markdown privately."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.draft_models import ApplicationActionDraftContent


class BookmarkDownloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    bookmark_id: UUID


class BookmarkDownloadSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: BookmarkDownloadInput
    answered_at: datetime
    answer_preview: str
    request_preview: str | None
    filename: str
    file_bytes: StrictInt = Field(ge=0)
    content_type: str = "text/markdown"
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"state_digest"})


class BookmarkDownloadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    saved_answer_to_download: BookmarkDownloadSnapshot


def canonical_bookmark_download(draft: ApplicationActionDraftContent) -> bool:
    scope = BookmarkDownloadPatch.model_validate(draft.intent).saved_answer_to_download
    return draft.before == {"saved_answer_to_download": None} and draft.after == {
        "saved_answer_to_download": scope.public_scope()
    }
