"""Finite source knowledge-space UI sections and exact page metadata."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from src.domains.rag_spaces.document_catalogue import AttachableDocument
from src.domains.rag_spaces.schemas import (
    RAGDocumentResponse,
    RAGDriveSourceResponse,
    RAGMailSourceResponse,
    RAGSpaceResponse,
)

SPACE_READ_MAX_PAGE = 50
SPACE_READ_MAX_BYTES = 64_000
SpaceReadSection = Literal[
    "spaces", "space", "documents", "drive_sources", "mail_sources", "attachable_documents"
]


class SpaceUIQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    section: SpaceReadSection = "spaces"
    space_id: UUID | None = None
    limit: StrictInt = Field(default=25, ge=1, le=SPACE_READ_MAX_PAGE)
    offset: StrictInt = Field(default=0, ge=0)
    q: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def section_requires_exact_identity(self) -> SpaceUIQuery:
        if (self.section not in {"spaces", "attachable_documents"}) != (self.space_id is not None):
            raise ValueError("An exact owned space_id is required only for a detail section")
        if self.section == "space" and (self.limit != 25 or self.offset != 0):
            raise ValueError("Paging applies to collections only")
        if self.q is not None and self.section != "attachable_documents":
            raise ValueError("Name search applies to the cross-space document catalogue only")
        return self


class SpaceUIProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: SpaceReadSection
    observed_at: datetime
    spaces: list[RAGSpaceResponse] = Field(default_factory=list)
    space: RAGSpaceResponse | None = None
    documents: list[RAGDocumentResponse] = Field(default_factory=list)
    attachable_documents: list[AttachableDocument] = Field(default_factory=list)
    drive_sources: list[RAGDriveSourceResponse] = Field(default_factory=list)
    mail_sources: list[RAGMailSourceResponse] = Field(default_factory=list)
    total: int | None = None
    next_offset: int | None = None
    technical_diagnostics_withheld: bool = False
