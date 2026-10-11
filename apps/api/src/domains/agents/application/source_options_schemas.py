"""Finite provider pickers; no query expression, account identity or import intent."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from src.domains.agents.application.space_read_schemas import SPACE_READ_MAX_PAGE
from src.domains.rag_spaces.schemas import GmailLabelResponse, RAGDrivePreflightResponse

SourceOptionsSection = Literal["drive_contents", "mail_labels", "drive_preflight"]


class SourceOptionsQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    section: SourceOptionsSection = Field(
        description="Drive/Gmail picker or existing Drive source preflight"
    )
    space_id: UUID = Field(description="A real current-account personal destination space")
    source_id: UUID | None = Field(
        default=None, description="Existing owned Drive source; required only for drive_preflight"
    )
    folder_id: str | None = Field(
        default=None,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Drive folder id; absent means root",
    )
    page_token: str | None = Field(
        default=None, max_length=4096, description="The previous Drive page's opaque continuation"
    )
    limit: StrictInt = Field(
        default=25,
        ge=1,
        le=SPACE_READ_MAX_PAGE,
        description="Maximum returned picker items; does not page preflight counts",
    )
    offset: StrictInt = Field(default=0, ge=0, description="Live Gmail label page offset")

    @model_validator(mode="after")
    def section_parameters(self) -> Self:
        if self.section == "drive_preflight":
            if (
                self.source_id is None
                or self.folder_id is not None
                or self.page_token is not None
                or self.offset != 0
            ):
                raise ValueError(
                    "Preflight requires an existing source id and accepts no picker navigation"
                )
        elif self.source_id is not None:
            raise ValueError("Only preflight accepts a linked source id")
        if self.section == "drive_contents" and self.offset != 0:
            raise ValueError("Drive paging uses the provider continuation only")
        if self.section == "mail_labels" and (
            self.folder_id is not None or self.page_token is not None
        ):
            raise ValueError("Gmail labels do not accept Drive parameters")
        return self


class DrivePickerItem(BaseModel):
    model_config = ConfigDict(extra="ignore", serialize_by_alias=True)
    id: str = Field(min_length=1, description="Real provider file or folder identity")
    name: str = Field(description="Literal provider display name")
    mime_type: str = Field(alias="mimeType", description="Source picker MIME type")
    modified_time: str | None = Field(
        default=None, alias="modifiedTime", description="Source picker modification timestamp"
    )


class DrivePickerPage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    files: list[DrivePickerItem] = Field(
        max_length=SPACE_READ_MAX_PAGE, description="Provider page, never silently cut"
    )
    next_page_token: str | None = Field(
        default=None,
        alias="nextPageToken",
        max_length=4096,
        description="Provider continuation, when present",
    )


class SourceOptionsProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: SourceOptionsSection = Field(description="Observed source picker")
    space_id: UUID = Field(description="Owned destination checked before and after the read")
    observed_at: datetime = Field(description="UTC observation time")
    source_id: UUID | None = Field(
        default=None, description="Existing Drive source observed before and after preflight"
    )
    source_name: str | None = Field(default=None, description="Literal current source name")
    preflight: RAGDrivePreflightResponse | None = Field(
        default=None,
        description="Source counts and bounds; truncated counts are floors. Its confirmation threshold is the GUI's; native actions always require HITL.",
    )
    drive_files: list[DrivePickerItem] = Field(
        default_factory=list, description="Public source picker fields only"
    )
    mail_labels: list[GmailLabelResponse] = Field(
        default_factory=list, description="User labels offered by the source picker"
    )
    total: int | None = Field(
        default=None, description="Exact Gmail label count; unknown for Drive"
    )
    next_page_token: str | None = Field(default=None, description="Live Drive continuation")
    next_offset: int | None = Field(default=None, description="Live Gmail continuation")
