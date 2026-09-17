"""Reading ONE mail attachment: its text when it has one, a vision reading otherwise.

The bytes a client downloaded (``EmailAttachmentContent``) are classified by
what they ARE — magic bytes first, the sender's header as a fallback — and
routed:

- a document the knowledge spaces already know how to read (the 15 formats
  of ``rag_spaces.processing.extract_text``) is extracted through that very
  pipeline, in a worker thread, from a temporary file it needs;
- an image, or a PDF whose pages carry pictures and no text layer (the shape
  of a scan — ``classify_empty_extraction``'s own reading), is handed to the
  ``vision_analysis`` slot as a bounded, downscaled set of pages;
- anything else is refused by name.

The vision call is the TURN's spend (``LLM_SPEND_ROADS``: TURN): it rides the
runtime's ``RunnableConfig`` so the ambient tracker records it, asks for a
short answer through the reasoning seam, refuses a truncated output as a
refusal (ADR-275) and steps aside under a ceiling refusal (``skipped_quota``
— a quota refusal is never a generation failure, ADR-272). Nothing here
touches a client: the bytes come in, a reading comes out.
"""

from __future__ import annotations

import asyncio
import base64
import io
import tempfile
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.core.constants import (
    ATTACHMENTS_ALLOWED_IMAGE_TYPES_DEFAULT,
    EMAIL_ATTACHMENT_PDF_RENDER_SCALE,
    RAG_SPACES_ALLOWED_TYPES_DEFAULT,
)
from src.core.i18n import get_language_name, normalize_language
from src.core.llm_config_helper import short_answer_config
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.prompts import load_prompt
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.rag_spaces.processing import extract_text
from src.domains.usage_limits.enforcement import spend_blocked
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.llm.output_truncation import is_output_truncated

logger = structlog.get_logger(__name__)

LLM_TYPE: Final = "vision_analysis"
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_OCTET_STREAM = "application/octet-stream"
#: Bytes ``filetype`` needs to decide; the sender's header decides below that.
_MAGIC_MIN_BYTES = 12

#: What the knowledge-space pipeline extracts, and what the vision slot sees.
TEXT_MIMES: frozenset[str] = frozenset(
    m.strip() for m in RAG_SPACES_ALLOWED_TYPES_DEFAULT.split(",") if m.strip()
)
IMAGE_MIMES: frozenset[str] = frozenset(
    m.strip() for m in ATTACHMENTS_ALLOWED_IMAGE_TYPES_DEFAULT.split(",") if m.strip()
)

VisionOutcome = Literal["ok", "truncated", "skipped_quota", "failed", "empty"]
ReadingOutcome = Literal["ok", "truncated", "skipped_quota", "failed", "empty", "unsupported"]


class Route(str, Enum):
    """How an attachment is read, decided on its bytes."""

    TEXT = "text"
    IMAGE = "image"
    VISION = "vision"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class VisionReading:
    """What the vision slot answered, or why it did not."""

    outcome: VisionOutcome
    text: str = ""


@dataclass(frozen=True, slots=True)
class RenderedPages:
    """The pages the vision slot sees, and how many the attachment holds."""

    pages: list[bytes]
    total: int


@dataclass(frozen=True, slots=True)
class AttachmentReading:
    """One attachment, read."""

    route: Route
    outcome: ReadingOutcome
    text: str
    mime_type: str
    #: Pages handed to the vision slot (0 on the text route).
    pages_read: int = 0
    #: Pages the attachment holds (0 on the text route): the cut is stated.
    pages_total: int = 0


def detect_mime(data: bytes, declared: str) -> str:
    """The MIME type of the bytes — magic bytes first, the header as a fallback."""
    if len(data) >= _MAGIC_MIN_BYTES:
        import filetype  # type: ignore[import-untyped]

        kind = filetype.guess(data)
        if kind is not None:
            return str(kind.mime)
    return declared.split(";")[0].strip() or _OCTET_STREAM


def route_of(mime_type: str) -> Route:
    """The route a MIME type takes: text extraction, the vision slot, or a refusal."""
    if mime_type in TEXT_MIMES:
        return Route.TEXT
    if mime_type in IMAGE_MIMES:
        return Route.IMAGE
    return Route.UNSUPPORTED


def _write_temp(data: bytes, suffix: str) -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with handle:
        handle.write(data)
    return Path(handle.name)


def _extract_from_temp(data: bytes, mime_type: str) -> str:
    path = _write_temp(data, suffix="")
    try:
        return extract_text(path, mime_type)
    finally:
        path.unlink(missing_ok=True)


async def extract_text_from_bytes(data: bytes, mime_type: str) -> str:
    """Extract the text of a document through the knowledge-space pipeline (worker thread)."""
    return await asyncio.to_thread(_extract_from_temp, data, mime_type)


def _pdf_has_images(data: bytes) -> bool:
    import fitz  # type: ignore[import-untyped]  # PyMuPDF

    with fitz.open(stream=data, filetype="pdf") as doc:
        return any(page.get_images() for page in doc)


async def is_scanned_pdf(data: bytes) -> bool:
    """A PDF whose pages carry pictures and no text layer — a scan (never raises)."""
    try:
        return await asyncio.to_thread(_pdf_has_images, data)
    except Exception:  # noqa: BLE001 — a PDF PyMuPDF cannot reopen is not a scan
        return False


def _downscale(image_bytes: bytes, max_edge: int) -> bytes:
    from PIL import Image

    from src.infrastructure.media.heif import ensure_heif_support

    ensure_heif_support()
    with Image.open(io.BytesIO(image_bytes)) as img:
        picture = img.convert("RGB") if img.mode not in ("RGB", "L") else img
        picture.thumbnail((max_edge, max_edge))
        buffer = io.BytesIO()
        picture.save(buffer, format="PNG")
        return buffer.getvalue()


def _render_pdf_pages(data: bytes, max_pages: int, max_edge: int) -> RenderedPages:
    import fitz  # PyMuPDF

    pages: list[bytes] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        total = len(doc)
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            # The bound applies to the RASTER, not only to the PNG handed to
            # the model: a page 200 inches a side at the nominal scale would
            # allocate gigabytes before any downscale. Twice the edge keeps
            # the downscale a reduction on an ordinary page.
            longest_pt = max(page.rect.width, page.rect.height, 1.0)
            scale = min(EMAIL_ATTACHMENT_PDF_RENDER_SCALE, (2 * max_edge) / longest_pt)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            pages.append(_downscale(pixmap.tobytes("png"), max_edge))
    return RenderedPages(pages=pages, total=total)


async def render_pages(
    data: bytes, mime_type: str, *, max_pages: int, max_edge: int
) -> RenderedPages:
    """The pages the vision slot sees: PNG bytes, bounded in count and in size.

    Args:
        data: The attachment bytes.
        mime_type: ``application/pdf`` or an image type.
        max_pages: Pages past which the rest is not shown.
        max_edge: Longest edge in pixels a page is downscaled to.

    Returns:
        One PNG per shown page, in page order, and the attachment's page count.
    """
    if mime_type == PDF_MIME:
        return await asyncio.to_thread(_render_pdf_pages, data, max_pages, max_edge)
    return RenderedPages(pages=[await asyncio.to_thread(_downscale, data, max_edge)], total=1)


@lru_cache(maxsize=1)
def _vision_lines() -> dict[str, str]:
    """One-line scaffolds of the vision reading, read once from the store."""
    return dict(parse_prompt_sections(read_prompt_file("email_attachment_vision_lines"), 2))


def _vision_message(rendered: RenderedPages, question: str | None, language: str) -> HumanMessage:
    lines = _vision_lines()
    shown = len(rendered.pages)
    cut_note = (
        lines["pages_cut"].format(shown=shown, total=rendered.total)
        if rendered.total > shown
        else ""
    )
    prompt = load_prompt("email_attachment_vision_prompt").format(
        language_name=get_language_name(normalize_language(language)),
        question=question or lines["default_question"],
        pages_note=cut_note,
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for page in rendered.pages:
        encoded = base64.b64encode(page).decode("ascii")
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
        )
    return HumanMessage(content=content)  # type: ignore[arg-type]


async def describe_with_vision(
    rendered: RenderedPages,
    *,
    question: str | None,
    language: str,
    user_id: str | None,
    config: RunnableConfig | None,
) -> VisionReading:
    """Ask the vision slot to read the pages — the turn's spend, bounded, refusable.

    Args:
        rendered: PNG pages (already bounded and downscaled) and the page count,
            so a cut set is STATED to the model rather than read as the whole.
        question: What the reader wants from the attachment, when stated.
        language: The reader's language (any spelling; normalised).
        user_id: The account, so both ceilings see the call.
        config: The turn's ``RunnableConfig`` — it carries the token-tracking
            callback; a model call handed no config is a euro no ledger sees.

    Returns:
        The reading, or why there is none.
    """
    if await spend_blocked(user_id):
        return VisionReading(outcome="skipped_quota")
    llm = get_llm(LLM_TYPE, config_override=short_answer_config(LLM_TYPE))
    message = _vision_message(rendered, question, language)
    try:
        response = await invoke_with_instrumentation(
            llm,
            LLM_TYPE,
            messages=[message],
            config=config,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001 — a provider failure is a refusal, not a crash
        logger.warning("email_attachment_vision_failed", error=str(exc)[:200])
        return VisionReading(outcome="failed")
    if is_output_truncated(response):
        return VisionReading(outcome="truncated")
    text = response.content if isinstance(response.content, str) else str(response.content)
    return VisionReading(outcome="ok" if text.strip() else "empty", text=text.strip())


async def read_attachment(
    content: EmailAttachmentContent,
    *,
    question: str | None,
    language: str,
    user_id: str | None,
    config: RunnableConfig | None,
    max_pages: int,
    max_edge: int,
) -> AttachmentReading:
    """Read one attachment: text when it has one, the vision slot otherwise.

    Args:
        content: The downloaded attachment.
        question: What the reader wants from it, when stated.
        language: The reader's language.
        user_id: The account the vision spend is charged to.
        config: The turn's ``RunnableConfig``.
        max_pages: Pages the vision slot may see.
        max_edge: Longest edge a page is downscaled to.

    Returns:
        The reading, its route and its outcome.
    """
    mime_type = detect_mime(content.data, content.mime_type)
    route = route_of(mime_type)
    if route is Route.UNSUPPORTED:
        return AttachmentReading(route, "unsupported", "", mime_type)

    if route is Route.TEXT:
        try:
            text = await extract_text_from_bytes(content.data, mime_type)
        except Exception as exc:  # noqa: BLE001 — a corrupt file is a refusal, not a crash
            logger.warning("email_attachment_extraction_failed", error=str(exc)[:200])
            return AttachmentReading(route, "failed", "", mime_type)
        if text.strip():
            return AttachmentReading(route, "ok", text.strip(), mime_type)
        if mime_type != PDF_MIME or not await is_scanned_pdf(content.data):
            return AttachmentReading(route, "empty", "", mime_type)
        # A scan: pictures and no text layer — read it with the vision slot.

    try:
        rendered = await render_pages(
            content.data, mime_type, max_pages=max_pages, max_edge=max_edge
        )
    except Exception as exc:  # noqa: BLE001 — an unreadable image is a refusal
        logger.warning("email_attachment_render_failed", error=str(exc)[:200])
        return AttachmentReading(Route.VISION, "failed", "", mime_type)
    reading = await describe_with_vision(
        rendered, question=question, language=language, user_id=user_id, config=config
    )
    return AttachmentReading(
        Route.VISION,
        reading.outcome,
        reading.text,
        mime_type,
        pages_read=len(rendered.pages),
        pages_total=rendered.total,
    )


__all__ = [
    "DOCX_MIME",
    "AttachmentReading",
    "RenderedPages",
    "Route",
    "VisionReading",
    "describe_with_vision",
    "detect_mime",
    "extract_text_from_bytes",
    "is_scanned_pdf",
    "read_attachment",
    "render_pages",
    "route_of",
]
