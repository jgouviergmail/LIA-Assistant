"""Bounded previews of generated documents; no retained bytes or model calls."""

import asyncio
import codecs
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.attachments.office_preview import OFFICE_FORMATS, office_excerpt

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_TEXT_BYTES = 65536
MAX_PNG_BYTES = 3 * 1024 * 1024
_PDF_SLOTS = threading.BoundedSemaphore(2)
_TEXT_TYPES = frozenset({"text/plain", "text/markdown", "text/csv"})


class PreviewUnavailable(ValueError):
    """No preview can be safely produced; the original document stays usable."""


@dataclass(frozen=True, slots=True)
class DocumentPreview:
    content: bytes
    media_type: str
    truncated: bool = False


def _read_source(attachment: Attachment, root: Path) -> tuple[bytes, bool]:
    path = (root / attachment.file_path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise PreviewUnavailable
    binary = attachment.mime_type == "application/pdf" or attachment.mime_type in OFFICE_FORMATS
    limit = MAX_PDF_BYTES if binary else MAX_TEXT_BYTES
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if binary and len(data) > limit:
        raise PreviewUnavailable
    return data[:limit], len(data) > limit


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
    if attachment.mime_type not in _TEXT_TYPES | {"application/pdf"} | OFFICE_FORMATS.keys():
        raise PreviewUnavailable
    try:
        data, truncated = await asyncio.to_thread(_read_source, attachment, root)
        if attachment.mime_type == "application/pdf":
            return DocumentPreview(await asyncio.to_thread(_run_pdf_worker, data), "image/png")
        if attachment.mime_type in OFFICE_FORMATS:
            try:
                content = await asyncio.to_thread(office_excerpt, data, attachment.mime_type)
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
