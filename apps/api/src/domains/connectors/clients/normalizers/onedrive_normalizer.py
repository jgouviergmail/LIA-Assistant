"""A Graph ``driveItem`` in the files vocabulary (ADR-369, lot 6).

Google's words are what the normalisers speak, as for the calendars: every reader of a file
reads ``mimeType``, ``modifiedTime``, ``parents``, ``owners``, and a folder is Drive's folder
type. Graph's size of a folder is the sum of what it holds, which Drive does not say of one:
it is left out, so a folder reads the same on both.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import unquote

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME

#: What a listing reads of each item.
DRIVE_ITEM_FIELDS: Final = (
    "id,name,size,file,folder,webUrl,lastModifiedDateTime,createdDateTime,"
    "parentReference,createdBy,description"
)
#: What an item with no ``file`` facet is said to be (a OneNote package has none).
_UNTYPED: Final = "application/octet-stream"


#: What Graph renders as a PDF (its documented list, a personal drive measured on 2026-11-05).
_PDF_SUFFIXES: Final = (
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".md",
    ".odp",
    ".ods",
    ".odt",
    ".ppt",
    ".pptx",
    ".rtf",
    ".xls",
    ".xlsm",
    ".xlsx",
)


def _folder_path(reference: Mapping[str, Any]) -> str | None:
    """An item's folders from the top of its drive; a feed entry names none, and None says so."""
    path = reference.get("path")
    if not isinstance(path, str) or ":" not in path:
        return None
    return unquote(path.split(":", 1)[1]).strip("/")


def _converts_to_pdf(item: Mapping[str, Any]) -> bool:
    """Whether Graph renders an item as a PDF: its name says, a folder never does."""
    named = str(item.get("name") or "").casefold()
    return "folder" not in item and named.endswith(_PDF_SUFFIXES)


def normalize_drive_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """An item as the files contract reads it.

    Args:
        item: A Graph ``driveItem``.

    Returns:
        The item in Drive's words; only what the item does say.
    """
    is_folder = "folder" in item
    file_facet = item.get("file") or {}
    reference = item.get("parentReference") or {}
    parent = reference.get("id")
    author = ((item.get("createdBy") or {}).get("user") or {}).get("displayName")
    normalized: dict[str, Any] = {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "mimeType": (
            GOOGLE_DRIVE_FOLDER_MIME if is_folder else file_facet.get("mimeType") or _UNTYPED
        ),
        "modifiedTime": item.get("lastModifiedDateTime"),
        "createdTime": item.get("createdDateTime"),
        "webViewLink": item.get("webUrl"),
        "parents": [parent] if parent else [],
        "owners": [{"displayName": author}] if author else [],
        "description": item.get("description"),
        "eTag": item.get("eTag"),
        "folderPath": _folder_path(reference),
        "pdfConvertible": _converts_to_pdf(item),
    }
    if not is_folder and item.get("size") is not None:
        normalized["size"] = item["size"]
    return normalized


__all__ = ["DRIVE_ITEM_FIELDS", "normalize_drive_item"]
