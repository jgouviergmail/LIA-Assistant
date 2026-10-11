"""Only a destination is model-selected; actual local file selection requires browser consent."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget


class DocumentUploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID


class DocumentUploadSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space: SpaceUpdateTarget
    document_count: StrictInt = Field(ge=0)
    max_documents: StrictInt = Field(ge=1)
    max_file_size_bytes: StrictInt = Field(ge=1)
    allowed_content_types: tuple[str, ...] = Field(min_length=1)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    @model_validator(mode="after")
    def bounded_scope(self) -> Self:
        if len(self.model_dump_json().encode("utf-8")) > 64_000:
            raise ValueError("An upload scope must fit within 64,000 bytes")
        return self

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "space": self.space.model_dump(mode="json"),
            "document_count": self.document_count,
            "max_documents": self.max_documents,
            "max_file_size_bytes": self.max_file_size_bytes,
            "allowed_content_types": list(self.allowed_content_types),
            "browser_file_confirmation_required": True,
            "indexing_requested": True,
            "indexing_cost_may_apply": True,
        }


class DocumentUploadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_to_upload: DocumentUploadSelection


class DocumentUploadField(StrEnum):
    DOCUMENT_TO_UPLOAD = "document_to_upload"


def canonical_document_upload(draft: ApplicationActionDraftContent) -> bool:
    selected = DocumentUploadPatch.model_validate(draft.intent).document_to_upload
    return draft.before == {"document_to_upload": None} and draft.after == {
        "document_to_upload": selected.public_scope()
    }
