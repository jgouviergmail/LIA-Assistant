"""Private account-file descriptor witness shared by deletion and browser transfer."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssetFileWitness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    stored_filename: str = Field(repr=False)
    file_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", repr=False)
