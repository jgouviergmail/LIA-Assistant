"""Closed exact archive selection, inheriting the source batch ceiling."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.constants import RAG_SPACES_BULK_MAX
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.rag_spaces.archive_schemas import DocumentArchiveSnapshot


class DocumentArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID
    document_ids: tuple[UUID, ...] = Field(min_length=1, max_length=RAG_SPACES_BULK_MAX)

    @field_validator("document_ids")
    @classmethod
    def distinct_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return tuple(dict.fromkeys(values))


class DocumentArchivePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    archive_to_download: DocumentArchiveSnapshot


def canonical_document_archive(draft: ApplicationActionDraftContent) -> bool:
    selected = DocumentArchivePatch.model_validate(draft.intent).archive_to_download
    return draft.before == {"archive_to_download": None} and draft.after == {
        "archive_to_download": selected.public_scope()
    }
