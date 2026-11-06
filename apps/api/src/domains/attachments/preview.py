"""Bounded previews of documents; no retained bytes or model calls.

A generated document is read from its stored file, a drive's file arrives as bytes: both reach
one reading, under the same bounds.
"""

import asyncio
import codecs
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from src.core.document_types import PDF_TYPE, TEXT_TYPES
from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.attachments.office_preview import OFFICE_FORMATS, office_excerpt

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_TEXT_BYTES = 65536
MAX_PNG_BYTES = 3 * 1024 * 1024
_PDF_SLOTS = threading.BoundedSemaphore(2)
#: A generated document's words; an HTML one is a page, shown as one elsewhere.
_GENERATED_TEXT_TYPES = frozenset({"text/plain", "text/markdown", "text/csv"})


class PreviewUnavailable(ValueError):
    """No preview can be safely produced; the original document stays usable."""


@dataclass(frozen=True, slots=True)
class DocumentPreview:
    content: bytes
    media_type: str
    truncated: bool = False


def is_previewable(mime_type: str) -> bool:
    """Whether a generated document of this type can be shown."""
    return mime_type in _GENERATED_TEXT_TYPES | {PDF_TYPE} | OFFICE_FORMATS.keys()


def _is_binary(mime_type: str) -> bool:
    return mime_type == PDF_TYPE or mime_type in OFFICE_FORMATS


def _read_limit(mime_type: str) -> int:
    return MAX_PDF_BYTES if _is_binary(mime_type) else MAX_TEXT_BYTES


def _within_limit(data: bytes, mime_type: str) -> tuple[bytes, bool]:
    """The bytes a reading takes, and whether it was cut; a binary is whole or nothing."""
    limit = _read_limit(mime_type)
    if _is_binary(mime_type) and len(data) > limit:
        raise PreviewUnavailable
    return data[:limit], len(data) > limit


def _read_source(attachment: Attachment, root: Path) -> tuple[bytes, bool]:
    path = (root / attachment.file_path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise PreviewUnavailable
    with path.open("rb") as source:
        data = source.read(_read_limit(attachment.mime_type) + 1)
    return _within_limit(data, attachment.mime_type)


def _run_pdf_worker(data: bytes) -> bytes:
    # MuPDF forbids threaded use. A child owns MuPDF; the thread only waits
    # for it. Holding the slot IN the thread survives caller cancellation.
    if not _PDF_SLOTS.acquire(blocking=False):
        raise PreviewUnavailable
    try:
        child = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("pdf_preview_worker.py"))],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
            env={key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ},
        )
        output = child.stdout
        if (
            child.returncode != 0
            or len(output) > MAX_PNG_BYTES
            or not output.startswith(b"\x89PNG\r\n\x1a\n")
        ):
            raise PreviewUnavailable
        return output
    except subprocess.TimeoutExpired as exc:
        raise PreviewUnavailable from exc
    finally:
        _PDF_SLOTS.release()


async def build_preview(attachment: Attachment, root: Path) -> DocumentPreview:
    """Read only known generated formats after caller-owned authorization."""
    if attachment.origin != AttachmentOrigin.GENERATED_DOCUMENT.value:
        raise PreviewUnavailable
    if not is_previewable(attachment.mime_type):
        raise PreviewUnavailable
    try:
        data, truncated = await asyncio.to_thread(_read_source, attachment, root)
    except (OSError, TimeoutError) as exc:
        raise PreviewUnavailable from exc
    return await _render(data, attachment.mime_type, truncated)


async def preview_of(data: bytes, mime_type: str) -> DocumentPreview:
    """A document that arrived as bytes, under the same bounds as a stored one.

    Args:
        data: The document.
        mime_type: Its type.

    Returns:
        What can be shown of it.

    Raises:
        PreviewUnavailable: Nothing can be shown of it.
    """
    if not (mime_type in TEXT_TYPES or is_previewable(mime_type)):
        raise PreviewUnavailable
    kept, truncated = _within_limit(data, mime_type)
    return await _render(kept, mime_type, truncated)


async def _render(data: bytes, mime_type: str, truncated: bool) -> DocumentPreview:
    try:
        if mime_type == PDF_TYPE:
            return DocumentPreview(await asyncio.to_thread(_run_pdf_worker, data), "image/png")
        if mime_type in OFFICE_FORMATS:
            try:
                content = await asyncio.to_thread(office_excerpt, data, mime_type)
            except ValueError as exc:
                raise PreviewUnavailable from exc
            return DocumentPreview(content, "text/plain", True)
        # A cut multibyte code point is withheld rather than replaced/invented.
        text = codecs.getincrementaldecoder("utf-8-sig")("replace").decode(
            data, final=not truncated
        )
        return DocumentPreview(text.encode("utf-8"), "text/plain", truncated)
    except (OSError, TimeoutError) as exc:
        raise PreviewUnavailable from exc
