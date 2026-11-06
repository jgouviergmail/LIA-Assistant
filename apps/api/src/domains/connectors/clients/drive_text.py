"""A drive's plain text file, read and written whole (ADR-369, lot 14).

Both drives hold these as bytes, so one implementation serves them through the file contract, and
the person's hand and the assistant share it (``TextFileDocuments``, what ``documents_of`` opens):
a tool names a file and never asks what it is. A text is written back on the version it was read
at (OneDrive's ``eTag``, Drive's head revision): a change made elsewhere meanwhile answers a
refusal, never a lost edit. What nobody can see in a text box stays as it was: a byte order mark,
Windows line ends. Bytes that are no UTF-8 are refused rather than guessed: rewriting them under a
wrong reading would damage every accented letter.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from typing import Any, Final

from src.core.constants import DRIVE_TEXT_MAX_BYTES
from src.core.document_types import is_text_type, reading_type
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal
from src.domains.connectors.clients.protocols import DocumentsProtocol

#: What a drive says of a file's version, on either: Graph answers its tag on every item.
_VERSION_FIELDS: Final = ["id", "name", "mimeType", "size", "headRevisionId"]
_GOOGLE_TYPE_PREFIX: Final = "application/vnd.google-apps."


@dataclass(frozen=True, slots=True)
class DriveText:
    """A text file's words, and the version they were read at."""

    name: str
    text: str
    tag: str


@dataclass(frozen=True, slots=True)
class _Held:
    """What a drive holds now."""

    item: dict[str, Any]
    data: bytes
    tag: str


def text_file_held_whole(mime_type: str, name: str, size: int | None) -> bool:
    """Whether a file is words that can be changed here, read whole.

    Args:
        mime_type: Its declared type.
        name: Its name.
        size: Its size, None when the drive gives none.

    Returns:
        True for a text within the bound.
    """
    return _is_text(mime_type, name) and size is not None and size <= DRIVE_TEXT_MAX_BYTES


async def read_text_file(drive: Any, file_id: str) -> DriveText:
    """A text file's words.

    Args:
        drive: An open drive client.
        file_id: The file.

    Returns:
        Its words, line ends as a text box shows them, and the version they were read at.

    Raises:
        OfficeContentRefusedError: It is no text, is past the bound, or holds no UTF-8.
    """
    held = await _held(drive, file_id)
    return DriveText(str(held.item.get("name") or ""), _words(held.data), held.tag)


async def rewrite_text_file(
    drive: Any, file_id: str, text: str, expected_tag: str
) -> dict[str, Any]:
    """Write a text file's words back, on the version they were read at.

    Args:
        drive: An open drive client.
        file_id: The file.
        text: Its new words.
        expected_tag: The version they were read at.

    Returns:
        The item as the drive answers it; as it was when the words did not change.

    Raises:
        OfficeContentRefusedError: It changed since, someone holds it locked, or the words pass
            the bound.
    """
    held = await _held(drive, file_id)
    if held.tag != expected_tag:
        raise OfficeContentRefusedError(OfficeRefusal.CHANGED)
    _words(held.data)
    data = _bytes(text, held.data)
    if len(data) > DRIVE_TEXT_MAX_BYTES:
        raise OfficeContentRefusedError(OfficeRefusal.TOO_LARGE)
    if data == held.data:
        return held.item
    written: dict[str, Any] = await drive.replace_content(
        file_id, data, str(held.item.get("mimeType") or ""), expected_tag
    )
    return written


async def append_to_text_file(drive: Any, file_id: str, addition: str) -> dict[str, Any]:
    """Add words at the end of a text file, on a line of their own.

    Args:
        drive: An open drive client.
        file_id: The file.
        addition: The words.

    Returns:
        The item as the drive answers it.

    Raises:
        OfficeContentRefusedError: As ``rewrite_text_file``.
    """
    read = await read_text_file(drive, file_id)
    joint = "\n" if read.text and not read.text.endswith("\n") else ""
    return await rewrite_text_file(drive, file_id, f"{read.text}{joint}{addition}\n", read.tag)


class TextFileDocuments:
    """A drive's documents, its plain text files among them (``DocumentsProtocol``)."""

    def __init__(self, drive: Any, documents: DocumentsProtocol) -> None:
        self._drive = drive
        self._documents = documents

    async def _names_a_text(self, document_id: str) -> bool:
        item = await self._drive.get_file_metadata(document_id, fields=_VERSION_FIELDS)
        return _is_text(str(item.get("mimeType") or ""), str(item.get("name") or ""))

    async def read_text(self, document_id: str) -> dict[str, str]:
        """A document's name and its text."""
        if not await self._names_a_text(document_id):
            return await self._documents.read_text(document_id)
        read = await read_text_file(self._drive, document_id)
        return {"title": read.name, "content": read.text}

    async def read_title(self, document_id: str) -> str:
        """A document's name, once it is one this drive can add to."""
        if not await self._names_a_text(document_id):
            return await self._documents.read_title(document_id)
        return (await read_text_file(self._drive, document_id)).name

    async def append_text(self, document_id: str, text: str) -> Any:
        """Add words at a document's end."""
        if not await self._names_a_text(document_id):
            return await self._documents.append_text(document_id, text)
        return await append_to_text_file(self._drive, document_id, text)

    async def read_version(self, document_id: str) -> DriveText:
        """A text file as a rewrite starts from it.

        Raises:
            OfficeContentRefusedError: It is no text: a document's words are not all it holds.
        """
        return await read_text_file(self._drive, document_id)

    async def replace_text(self, document_id: str, text: str, expected_tag: str) -> Any:
        """Rewrite a text file, on the version a rewrite started from."""
        return await rewrite_text_file(self._drive, document_id, text, expected_tag)


def _is_text(mime_type: str, name: str) -> bool:
    if mime_type.startswith(_GOOGLE_TYPE_PREFIX):
        return False
    return is_text_type(reading_type(mime_type, name))


async def _held(drive: Any, file_id: str) -> _Held:
    item: dict[str, Any] = await drive.get_file_metadata(file_id, fields=_VERSION_FIELDS)
    if not _is_text(str(item.get("mimeType") or ""), str(item.get("name") or "")):
        raise OfficeContentRefusedError(OfficeRefusal.NOT_THIS_FORMAT)
    size = int(item.get("size") or 0)
    if size > DRIVE_TEXT_MAX_BYTES:
        raise OfficeContentRefusedError(OfficeRefusal.TOO_LARGE)
    tag = item.get("eTag") or item.get("headRevisionId")
    if not isinstance(tag, str) or not tag:
        raise OfficeContentRefusedError(OfficeRefusal.UNREADABLE)
    data = await drive.get_file_content(
        file_id, max_size_bytes=DRIVE_TEXT_MAX_BYTES, known_size=size
    )
    if data is None:
        raise OfficeContentRefusedError(OfficeRefusal.TOO_LARGE)
    return _Held(item, data, tag)


def _words(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise OfficeContentRefusedError(OfficeRefusal.UNREADABLE) from error
    return text.replace("\r\n", "\n")


def _bytes(text: str, like: bytes) -> bytes:
    """Words as a file's bytes, in the file's own line ends and with its own mark."""
    body = text.replace("\r\n", "\n")
    if like.count(b"\r\n") * 2 > like.count(b"\n"):
        body = body.replace("\n", "\r\n")
    mark = codecs.BOM_UTF8 if like.startswith(codecs.BOM_UTF8) else b""
    return mark + body.encode()


__all__ = [
    "DriveText",
    "TextFileDocuments",
    "append_to_text_file",
    "read_text_file",
    "rewrite_text_file",
    "text_file_held_whole",
]
