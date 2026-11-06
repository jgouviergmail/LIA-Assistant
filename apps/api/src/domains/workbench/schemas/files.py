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
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from src.core.config import settings
from src.core.constants import (
    DRIVE_TEXT_MAX_BYTES,
    WORKBENCH_FILE_NAME_MAX_CHARS,
    WORKBENCH_FILE_TAG_MAX_CHARS,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
)
from src.domains.workbench.drive_formats import DriveKind, ExportFormat
from src.domains.workbench.ids import OptionalPageToken, OptionalProviderId, ProviderId

_Words = Annotated[
    str | None,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS
    ),
]


_NAME = StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=WORKBENCH_FILE_NAME_MAX_CHARS,
    pattern=r"^[^\x00-\x1f\x7f/\\]+$",
)
#: One name, never a path: OneDrive refuses what Drive would take.
FileName = Annotated[str, _NAME]
OptionalFileName = Annotated[str | None, _NAME]

#: What a person may be given on a file; nobody is made its owner here.
ShareRole = Literal["reader", "writer"]

#: What a drive keeps across its folders, where it keeps it.
FilesView = Literal["recent", "starred", "shared", "trash", "drives"]

#: How a folder is ordered: by Drive, the listing being paged.
FilesOrder = Literal["name", "modified", "size"]


class FilesQuery(BaseModel):
    """A folder's page (My Drive when none is named), or a Drive-wide search."""

    model_config = ConfigDict(extra="forbid")

    folder_id: OptionalProviderId = Field(default=None, description="The folder; My Drive if none.")
    q: _Words = Field(default=None, description="The words searched, Drive-wide.")
    full_text: bool = Field(default=False, description="Search the content too, not only names.")
    view: FilesView | None = Field(default=None, description="A view across the folders.")
    page_token: OptionalPageToken = Field(default=None, description="The next page's token.")
    order: FilesOrder = Field(default="name", description="A folder's order, folders first.")

    @model_validator(mode="after")
    def _one_listing(self) -> Self:
        if self.q is not None and self.folder_id is not None:
            raise ValueError("a search is Drive-wide, never inside one folder")
        if self.q is not None and self.order != "name":
            raise ValueError("a search has Drive's own order")
        if self.view is not None and (
            self.q is not None or self.folder_id is not None or self.order != "name"
        ):
            raise ValueError("a view stands alone, in Drive's own order")
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
    starred: bool = Field(default=False, description="The person starred it.")
    previewable: bool = Field(default=False, description="Something can be shown of it.")
    editable: bool = Field(default=False, description="Its words can be changed here.")


class FilesPage(BaseModel):
    """A page of a folder or of a search — Drive's cursor says whether more follow."""

    items: list[DriveItem] = Field(description="The items of this page.")
    next_page_token: str | None = Field(description="The next page's token; None on the last.")


class DriveQuota(BaseModel):
    """What the account uses of its drive."""

    model_config = ConfigDict(frozen=True)

    used: int = Field(description="The bytes used.")
    total: int | None = Field(description="The bytes it has; None for an unlimited account.")


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


class FileText(BaseModel):
    """A text file's words, and the version a change must name."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(description="Its words, line ends as a text box shows them.")
    tag: str = Field(description="The version they were read at.")


class FileTextChange(BaseModel):
    """A text file's new words, on the version they were read at."""

    model_config = ConfigDict(extra="forbid")

    id: ProviderId = Field(description="The file.")
    text: Annotated[str, StringConstraints(max_length=DRIVE_TEXT_MAX_BYTES)] = Field(
        description="Its new words."
    )
    tag: Annotated[
        str, StringConstraints(min_length=1, max_length=WORKBENCH_FILE_TAG_MAX_CHARS)
    ] = Field(description="The version they were read at.")


class NewFolder(BaseModel):
    """A folder to create, once per submission."""

    model_config = ConfigDict(extra="forbid")

    name: FileName = Field(description="Its name.")
    folder_id: OptionalProviderId = Field(default=None, description="Its parent; the top if none.")
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")


class FileRename(BaseModel):
    """An item's new name."""

    model_config = ConfigDict(extra="forbid")

    file_id: ProviderId = Field(description="The item.")
    name: FileName = Field(description="Its new name.")


class FileStar(BaseModel):
    """An item's star."""

    model_config = ConfigDict(extra="forbid")

    file_id: ProviderId = Field(description="The item.")
    starred: bool = Field(description="Its star.")


class FileMove(BaseModel):
    """Files going to a folder: the published bulk bound at most."""

    model_config = ConfigDict(extra="forbid")

    file_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=settings.workbench_bulk_max_items,
        description="The selection (at most the published bulk bound).",
    )
    folder_id: OptionalProviderId = Field(
        default=None, description="The folder they go to; the top if none."
    )


class FileCopy(BaseModel):
    """A file to copy."""

    model_config = ConfigDict(extra="forbid")

    file_id: ProviderId = Field(description="The file.")
    folder_id: OptionalProviderId = Field(
        default=None, description="The folder it goes to; beside the original if none."
    )
    name: OptionalFileName = Field(default=None, description="Its name; the provider's if none.")
    idempotency_key: UUID = Field(description="One key per submission (a replay copies nothing).")


class FileFromMail(BaseModel):
    """A mail's attachment going to a folder, once per submission."""

    model_config = ConfigDict(extra="forbid")

    message_id: ProviderId = Field(description="Its message.")
    attachment_id: OptionalProviderId = Field(
        default=None, description="Its handle, if it has one."
    )
    filename: OptionalFileName = Field(default=None, description="Its name, if it has one.")
    folder_id: OptionalProviderId = Field(default=None, description="Its folder; the top if none.")
    idempotency_key: UUID = Field(description="One key per submission (a replay sends nothing).")

    @model_validator(mode="after")
    def _is_named(self) -> Self:
        if self.attachment_id is None and self.filename is None:
            raise ValueError("an attachment is named by its handle or its name")
        return self


class FileRef(BaseModel):
    """One item an act is about."""

    model_config = ConfigDict(extra="forbid")

    file_id: ProviderId = Field(description="The item.")


class FileShare(BaseModel):
    """A person given access to an item, once per submission."""

    model_config = ConfigDict(extra="forbid")

    file_id: ProviderId = Field(description="The item.")
    email: EmailStr = Field(description="Their address: the drive tells them.")
    role: ShareRole = Field(description="What they may do.")
    idempotency_key: UUID = Field(description="One key per submission (a replay tells nobody).")


class FileShareRemoval(BaseModel):
    """An access taken back."""

    model_config = ConfigDict(extra="forbid")

    file_id: ProviderId = Field(description="The item.")
    permission_id: ProviderId = Field(description="The access.")


class SharedLink(BaseModel):
    """The link anyone can follow; no address when the drive answered none that opens."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The drive's id of the link.")
    url: str | None = Field(description="Its address (https alone).")


class SharedPerson(BaseModel):
    """Someone who reaches an item."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The drive's id of the access.")
    email: str | None = Field(description="Their address, if the drive names it.")
    name: str | None = Field(description="Their name, if the drive names it.")
    role: Literal["owner", "writer", "reader"] = Field(description="What they may do.")


class FileSharing(BaseModel):
    """Who reaches an item."""

    people: list[SharedPerson] = Field(description="Who was given access.")
    link: SharedLink | None = Field(description="The link anyone can follow, if it has one.")


class FileCopied(BaseModel):
    """What a copy answers."""

    item: DriveItem | None = Field(
        description="The copy; None while the provider finishes it (OneDrive)."
    )


class FileSelection(BaseModel):
    """The files one act is about: one at least, the published bulk bound at most."""

    model_config = ConfigDict(extra="forbid")

    file_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=settings.workbench_bulk_max_items,
        description="The selection (at most the published bulk bound).",
    )
