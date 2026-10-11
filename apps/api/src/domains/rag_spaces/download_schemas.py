"""Stored-document download identity carries public metadata and private comparison only."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt


class DocumentDownloadSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID
    document_id: UUID
    space_name: str
    original_filename: str
    content_type: str
    file_size_bytes: StrictInt = Field(ge=0)
    file_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"file_digest", "source_digest"})
