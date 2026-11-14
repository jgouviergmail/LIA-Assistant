"""What an uploaded document IS — decided by its bytes, never by what the browser claims.

The composer took images and PDFs, each recognised by its signature. It takes
every format the knowledge spaces read (ADR-295 amendment 2026-11-12): a copy
from a space already brought any of them into a message, so the upload accepts
what the copy accepts. The table below names them once; the spaces' extractor
table is asserted to cover it at import.

Two families, two proofs:

- a **signed** format (PDF, RTF, the Office and OpenDocument archives, EPUB)
  is recognised by its bytes. The archives open on the same four bytes, so an
  archive is told apart by what it CONTAINS: the part an Office file is built
  around, or the ``mimetype`` member an OpenDocument or EPUB file declares
  itself with. An archive holding neither is no document, whatever its name;
- an **unsigned** one (plain text, Markdown, CSV, HTML, JSON, XML) has no
  signature to read. Its NAME says which text it is, and its content must BE
  text: a byte no text file holds refuses it. A legacy encoding stays text —
  a spreadsheet export from a French desktop is cp1252, and readable — and so
  does Windows' « Unicode » text, UTF-16 behind its byte-order mark, whose
  NUL bytes are half of its letters.

The declared content type of the request is never read.
"""

from __future__ import annotations

import codecs
import io
import zipfile
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Final

import structlog

from src.core.config import settings
from src.domains.rag_spaces.processing import EXTRACTABLE_CONTENT_TYPES, extract_text

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentFormat:
    """One document format the chat accepts.

    Attributes:
        mime_type: What the stored attachment is recorded as, and the key of
            its extractor.
        extensions: The names it is known under; the first is the suffix a
            stored file takes.
        signed: Whether its bytes say what it is. An unsigned format is text,
            named by its extension.
    """

    mime_type: str
    extensions: tuple[str, ...]
    signed: bool


_DOCX: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPTX: Final = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_ODT: Final = "application/vnd.oasis.opendocument.text"
_ODS: Final = "application/vnd.oasis.opendocument.spreadsheet"
_ODP: Final = "application/vnd.oasis.opendocument.presentation"
_EPUB: Final = "application/epub+zip"
_PDF: Final = "application/pdf"
_RTF: Final = "application/rtf"

DOCUMENT_FORMATS: Final[tuple[DocumentFormat, ...]] = (
    DocumentFormat(_PDF, (".pdf",), signed=True),
    DocumentFormat(_DOCX, (".docx",), signed=True),
    DocumentFormat(_XLSX, (".xlsx",), signed=True),
    DocumentFormat(_PPTX, (".pptx",), signed=True),
    DocumentFormat(_ODT, (".odt",), signed=True),
    DocumentFormat(_ODS, (".ods",), signed=True),
    DocumentFormat(_ODP, (".odp",), signed=True),
    DocumentFormat(_EPUB, (".epub",), signed=True),
    DocumentFormat(_RTF, (".rtf",), signed=True),
    DocumentFormat("text/plain", (".txt",), signed=False),
    DocumentFormat("text/markdown", (".md",), signed=False),
    DocumentFormat("text/csv", (".csv",), signed=False),
    DocumentFormat("text/html", (".html", ".htm"), signed=False),
    DocumentFormat("application/json", (".json",), signed=False),
    DocumentFormat("application/xml", (".xml",), signed=False),
    # The same reader under its second name: nothing is detected as it, an
    # operator's allowlist may still spell it.
    DocumentFormat("text/xml", (), signed=False),
)

_BY_MIME: Final[dict[str, DocumentFormat]] = {fmt.mime_type: fmt for fmt in DOCUMENT_FORMATS}
_TEXT_BY_EXTENSION: Final[dict[str, str]] = {
    extension: fmt.mime_type
    for fmt in DOCUMENT_FORMATS
    if not fmt.signed
    for extension in fmt.extensions
}

#: The signatures that say everything by themselves.
_SELF_DESCRIBING: Final[frozenset[str]] = frozenset({_PDF, _RTF})
#: The part an Office Open XML package is built around, by kind.
_OFFICE_PARTS: Final[dict[str, str]] = {
    "word/document.xml": _DOCX,
    "xl/workbook.xml": _XLSX,
    "ppt/presentation.xml": _PPTX,
}
_OFFICE_MANIFEST: Final = "[Content_Types].xml"
#: The member an OpenDocument or EPUB archive declares itself with, and what it
#: may say. It is a few dozen bytes: a larger one is not that member.
_DECLARATION_MEMBER: Final = "mimetype"
_DECLARATION_MAX_BYTES: Final = 128
_DECLARED_ARCHIVES: Final[frozenset[str]] = frozenset({_ODT, _ODS, _ODP, _EPUB})
#: Every format that is a zip archive: what its readers inflate is bounded.
_ARCHIVE_FORMATS: Final[frozenset[str]] = _DECLARED_ARCHIVES | frozenset(_OFFICE_PARTS.values())
_ARCHIVE_SIGNATURE: Final = b"PK\x03\x04"
#: No text file holds this byte; nearly every binary one does — but for a text
#: Windows writes as UTF-16, which says so by its byte-order mark.
_NUL: Final = b"\x00"
_UTF16_MARKS: Final = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)


def _assert_formats_are_extractable() -> None:
    """Refuse to import with a format nothing can read.

    Raises:
        RuntimeError: When a declared format has no extractor.
    """
    unread = sorted(set(_BY_MIME) - EXTRACTABLE_CONTENT_TYPES)
    if unread:
        raise RuntimeError(f"Document formats without an extractor: {unread}")


def assert_document_formats_extractable() -> None:
    """Public form of the import-time assert, for the guard that names it."""
    _assert_formats_are_extractable()


_assert_formats_are_extractable()


def detect_document_type(filename: str, content: bytes) -> str | None:
    """The MIME type of an uploaded document, from what it is.

    Args:
        filename: The name it was sent under — read for an UNSIGNED format
            only, to tell which text it is.
        content: Its whole content, already bounded by the caller.

    Returns:
        The MIME type of a declared format, or ``None`` when the content is
        none of them (or is empty).
    """
    if not content:
        return None
    signed = _signed_type(content)
    if signed is not None:
        return signed
    if _NUL in content and not _is_utf16_text(content):
        return None
    return _TEXT_BY_EXTENSION.get(PurePath(filename).suffix.lower())


def _is_utf16_text(content: bytes) -> bool:
    """Whether the bytes are a text Windows wrote as UTF-16, behind its byte-order mark.

    Every ASCII letter of such a text carries a NUL byte, the byte that refuses a
    binary. The MARK says what the text is, and the text it says must be
    letters: it decodes whole, and it holds no NUL character — a binary opening
    on the same two bytes does neither.

    Args:
        content: The whole upload, already bounded by the caller.

    Returns:
        True for a UTF-16 text behind its mark.
    """
    if not content.startswith(_UTF16_MARKS):
        return False
    try:
        text = content.decode("utf-16")
    except UnicodeDecodeError:
        return False
    return "\x00" not in text


def _signed_type(content: bytes) -> str | None:
    """The format the bytes themselves name, or ``None``."""
    if content.startswith(_ARCHIVE_SIGNATURE):
        return _archive_type(content)
    import filetype  # type: ignore[import-untyped]

    kind = filetype.guess(content)
    return kind.mime if kind is not None and kind.mime in _SELF_DESCRIBING else None


def _archive_type(content: bytes) -> str | None:
    """Which document an archive is, read from its members; ``None`` for any other archive.

    Only the member NAMES and one tiny member are read: nothing is inflated
    beyond ``_DECLARATION_MAX_BYTES``.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if _OFFICE_MANIFEST in names:
                for part, mime_type in _OFFICE_PARTS.items():
                    if part in names:
                        return mime_type
            if _DECLARATION_MEMBER not in names:
                return None
            member = archive.getinfo(_DECLARATION_MEMBER)
            if member.file_size > _DECLARATION_MAX_BYTES:
                return None
            declared = archive.read(member).decode("ascii", errors="replace").strip()
    except zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError, RuntimeError:
        # A truncated, encrypted or malformed archive is no document.
        return None
    return declared if declared in _DECLARED_ARCHIVES else None


def extract_capped_text(path: Path, mime_type: str, max_chars: int) -> str | None:
    """A stored document's text, through the knowledge spaces' reader, capped.

    An extraction that fails costs the text, never the upload — as a scanned
    PDF always did: the person still sees their file, and the model is not
    handed a document it cannot read. An archive that declares more than
    ``ATTACHMENTS_MAX_INFLATED_MB`` once inflated is not opened by its reader
    at all (:func:`_inflates_too_far`).

    Args:
        path: The stored file.
        mime_type: Its format — the key of its reader.
        max_chars: The attachments' text cap.

    Returns:
        The text cut at ``max_chars``, or ``None`` when there is none to read.
    """
    if _inflates_too_far(path, mime_type):
        return None
    try:
        text = extract_text(path, mime_type)
    except Exception as exc:  # noqa: BLE001 — a text never costs the upload
        # Facts only (ADR-317): a reader's message may quote the document.
        logger.warning(
            "attachment_text_extraction_failed",
            mime_type=mime_type,
            error_type=type(exc).__name__,
        )
        return None
    return text[:max_chars] or None


def _inflates_too_far(path: Path, mime_type: str) -> bool:
    """Whether a zipped document declares more than its readers may inflate.

    A document sent small can inflate large — megabytes of padding deflate to a
    few kilobytes — and its readers inflate whole parts in memory, inside the
    upload request. What an archive inflates to is DECLARED in its directory,
    and the zip readers never inflate a member past what it declares: the sum
    is a real bound, read without inflating anything.

    Args:
        path: The stored file.
        mime_type: Its format; only an archive format is measured.

    Returns:
        True when the text must not be read; the fact is logged, never the name.
    """
    if mime_type not in _ARCHIVE_FORMATS:
        return False
    ceiling = settings.attachments_max_inflated_mb * 1024 * 1024
    try:
        with zipfile.ZipFile(path) as archive:
            inflated = sum(member.file_size for member in archive.infolist())
    except zipfile.BadZipFile, zipfile.LargeZipFile, OSError:
        # Unreadable as an archive: its reader will say so, and cost the text alone.
        return False
    if inflated <= ceiling:
        return False
    logger.warning(
        "attachment_text_extraction_skipped",
        mime_type=mime_type,
        reason="inflated_size",
        inflated_mb=inflated // (1024 * 1024),
        ceiling_mb=settings.attachments_max_inflated_mb,
    )
    return True


def extension_of(mime_type: str) -> str | None:
    """The suffix a stored file of this format takes, or ``None`` for an unknown one."""
    fmt = _BY_MIME.get(mime_type)
    return fmt.extensions[0] if fmt is not None and fmt.extensions else None


def accepted_extensions(allowed_mime_types: Collection[str]) -> list[str]:
    """The file extensions the composer may offer, for the types the instance allows.

    Published to the web (ADR-184): a browser reports no usable type for a
    ``.md`` or a ``.csv``, so the picker and the drop zone filter on names.

    Args:
        allowed_mime_types: The instance's allowed types (others are ignored).

    Returns:
        The extensions, sorted.
    """
    return sorted(
        extension
        for fmt in DOCUMENT_FORMATS
        if fmt.mime_type in allowed_mime_types
        for extension in fmt.extensions
    )


def composer_accepts() -> dict[str, list[str]]:
    """What the composer may offer, from the instance's own allowlists.

    Returns:
        ``image_types`` (MIME types) and ``document_extensions`` (file
        extensions), each sorted — the two filters of the picker and the drop zone.
    """
    return {
        "image_types": sorted(_listed(settings.attachments_allowed_image_types)),
        "document_extensions": accepted_extensions(_listed(settings.attachments_allowed_doc_types)),
    }


def _listed(setting: str) -> set[str]:
    """The entries of a comma-separated allowlist setting."""
    return {entry.strip() for entry in setting.split(",") if entry.strip()}


__all__ = [
    "DOCUMENT_FORMATS",
    "DocumentFormat",
    "accepted_extensions",
    "composer_accepts",
    "assert_document_formats_extractable",
    "detect_document_type",
    "extension_of",
    "extract_capped_text",
]
