"""What a Drive file is, and what it downloads as (ADR-369).

A Google document (Docs, Sheets, Slides) has no bytes of its own: it is
EXPORTED, to the formats a desktop opens — Docs to PDF or DOCX, Sheets to XLSX,
Slides to PDF or PPTX, the first one the default. Every other Google type (a
form, a site, a map, a folder) downloads as nothing: it opens in Drive. A
shortcut points at a file or a folder elsewhere and is drawn as such. Any other
file downloads as its own bytes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

FOLDER_MIME: Final = "application/vnd.google-apps.folder"
SHORTCUT_MIME: Final = "application/vnd.google-apps.shortcut"
_GOOGLE_TYPE_PREFIX: Final = "application/vnd.google-apps."

ExportFormat = Literal["pdf", "docx", "xlsx", "pptx"]
PDF_EXPORT: Final[ExportFormat] = "pdf"
DriveKind = Literal["folder", "file", "shortcut"]


@dataclass(frozen=True)
class Export:
    """A format a Google document leaves as."""

    mime_type: str
    extension: str


_PDF: Final = Export("application/pdf", "pdf")
_DOCX: Final = Export(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"
)
_XLSX: Final = Export("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")
_PPTX: Final = Export(
    "application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx"
)

#: Each exportable Google type, its formats in the order offered (the first the default).
EXPORTS: Final[Mapping[str, Mapping[ExportFormat, Export]]] = {
    "application/vnd.google-apps.document": {"pdf": _PDF, "docx": _DOCX},
    "application/vnd.google-apps.spreadsheet": {"xlsx": _XLSX},
    "application/vnd.google-apps.presentation": {"pdf": _PDF, "pptx": _PPTX},
}


def kind_of(mime_type: str) -> DriveKind:
    """A folder, a shortcut, or a file."""
    if mime_type == FOLDER_MIME:
        return "folder"
    if mime_type == SHORTCUT_MIME:
        return "shortcut"
    return "file"


def is_google_type(mime_type: str) -> bool:
    """A Google type: no bytes of its own."""
    return mime_type.startswith(_GOOGLE_TYPE_PREFIX)


def formats_of(mime_type: str) -> list[ExportFormat]:
    """The formats a Google document exports to; none for any other file."""
    return list(EXPORTS.get(mime_type, {}))


def is_downloadable(mime_type: str) -> bool:
    """Bytes of its own, or a Google document with an export."""
    return mime_type in EXPORTS if is_google_type(mime_type) else True
