"""The model chooses an owned export id; the source supplies its immutable identity."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.infrastructure.account_export_downloads import ExportArchiveSnapshot


class ExportDownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_id: UUID


class ExportDownloadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    archive_to_download: ExportArchiveSnapshot
