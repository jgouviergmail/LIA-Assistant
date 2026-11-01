"""What the files routes take and answer (ADR-369).

A folder is listed by cursor, and so is a search — Drive-wide (a folder's « in
parents » reaches its direct children only, so « search this folder » would
quietly miss its sub-folders); Drive may answer a partial page before the end,
so only its cursor says more follow. A file says what it is (a folder, a shortcut and its target, a file)
and what it downloads as. A breadcrumb walks up to My Drive under a bounded
depth and says when it stopped, or that the file lives outside My Drive.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.core.config import settings
from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.domains.workbench.drive_formats import DriveKind, ExportFormat
from src.domains.workbench.ids import OptionalPageToken, OptionalProviderId, ProviderId

_Words = Annotated[
    str | None,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS
    ),
]


class FilesQuery(BaseModel):
    """A folder's page (My Drive when none is named), or a Drive-wide search."""

    model_config = ConfigDict(extra="forbid")

    folder_id: OptionalProviderId = Field(default=None, description="The folder; My Drive if none.")
    q: _Words = Field(default=None, description="The words searched, Drive-wide.")
    full_text: bool = Field(default=False, description="Search the content too, not only names.")
    page_token: OptionalPageToken = Field(default=None, description="The next page's token.")

    @model_validator(mode="after")
    def _one_listing(self) -> Self:
        if self.q is not None and self.folder_id is not None:
            raise ValueError("a search is Drive-wide, never inside one folder")
        return self


class DriveItem(BaseModel):
    """One folder, shortcut or file as the list draws it."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Drive's id of the item.")
    name: str = Field(description="Its name.")
    kind: DriveKind = Field(description="A folder, a shortcut, or a file.")
    mime_type: str = Field(description="Its type as Drive declares it.")
    modified_at: datetime | None = Field(description="When it last changed.")
    size: int | None = Field(description="Its size in bytes; None for a Google document.")
    web_url: str | None = Field(description="Where Drive opens it (Google's own https link).")
    target_id: str | None = Field(description="A shortcut's target.")
    target_kind: DriveKind | None = Field(description="What a shortcut points at.")
    formats: list[ExportFormat] = Field(
        description="The formats a Google document exports to (the first the default)."
    )
    downloadable: bool = Field(description="It has bytes, or a Google document with an export.")


class FilesPage(BaseModel):
    """A page of a folder or of a search — Drive's cursor says whether more follow."""

    items: list[DriveItem] = Field(description="The items of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")


class FileAncestor(BaseModel):
    """One folder of a breadcrumb."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The folder.")
    name: str = Field(description="Its name.")


class FileDetail(DriveItem):
    """One item, and where it lives."""

    owners: list[str] = Field(description="Its owners' names.")
    description: str | None = Field(description="Its description.")
    created_at: datetime | None = Field(description="When it was created.")
    ancestors: list[FileAncestor] = Field(
        description="Its folders from the top down, My Drive itself left out."
    )
    in_my_drive: bool = Field(description="The walk reached My Drive.")
    ancestors_truncated: bool = Field(
        description="The walk stopped at its depth: folders above it are not shown."
    )


class DownloadQuery(BaseModel):
    """A file to download, and the format a Google document leaves as."""

    model_config = ConfigDict(extra="forbid")

    id: ProviderId = Field(description="The file.")
    format: ExportFormat | None = Field(
        default=None, description="A Google document's export format; its first when unsaid."
    )


class FileSelection(BaseModel):
    """The files one act is about: one at least, the published bulk bound at most."""

    model_config = ConfigDict(extra="forbid")

    file_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=settings.workbench_bulk_max_items,
        description="The selection (at most the published bulk bound).",
    )
