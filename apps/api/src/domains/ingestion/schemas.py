"""Public source/credential metadata; secrets only exist in issuance responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.ingestion.registry import IngestionResource


class IngestionTokenRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    source_id: UUID
    resource: IngestionResource
    label: str | None
    token_prefix: str
    scopes: tuple[str, ...]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class IngestionTokenSecret(IngestionTokenRow):
    token: str = Field(repr=False)


class IngestionTokenSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    token: IngestionTokenRow
    digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.token.model_dump(mode="json")
