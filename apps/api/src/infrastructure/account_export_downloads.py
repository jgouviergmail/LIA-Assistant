"""Typed archive identity and bounded byte access; paths never enter assistant data."""

from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, StrictStr


class ExportArchiveSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_id: UUID
    created_at: AwareDatetime
    completed_at: AwareDatetime | None
    expires_at: AwareDatetime
    file_size_bytes: StrictInt = Field(ge=0)
    archive_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class ExportArchiveRead(Protocol):
    @property
    def snapshot(self) -> ExportArchiveSnapshot: ...

    async def read_chunk(self) -> bytes: ...

    async def close(self) -> None: ...


class ExportDownloadCompletionUnknown(RuntimeError):
    """A download audit may have committed; the initiating command must not replay."""
