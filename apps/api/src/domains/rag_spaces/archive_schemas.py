"""Exact selected archive metadata, with file identities kept outside public previews."""

import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt, model_validator

from src.core.constants import RAG_SPACES_BULK_MAX

ARCHIVE_METADATA_MAX_BYTES = 64_000


class ArchiveDocumentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: UUID
    original_filename: str
    member_name: str
    file_size_bytes: StrictInt = Field(ge=0)
    present: StrictBool
    file_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", repr=False)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    @model_validator(mode="after")
    def require_exact_file_identity(self) -> ArchiveDocumentSnapshot:
        if self.present != (self.file_digest is not None):
            raise ValueError("A present file requires its identity; a missing file has none")
        return self

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"file_digest", "source_digest"})


class DocumentArchiveSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID
    space_name: str
    documents: tuple[ArchiveDocumentSnapshot, ...] = Field(
        min_length=1, max_length=RAG_SPACES_BULK_MAX
    )

    @model_validator(mode="after")
    def require_distinct_documents(self) -> DocumentArchiveSnapshot:
        if len({document.document_id for document in self.documents}) != len(self.documents):
            raise ValueError("Archive identities must be distinct")
        if (
            len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False).encode("utf-8"))
            > ARCHIVE_METADATA_MAX_BYTES
        ):
            raise ValueError("Archive consent is too large; select fewer documents")
        return self

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "space_id": str(self.space_id),
            "space_name": self.space_name,
            "documents": [document.public_scope() for document in self.documents],
        }
