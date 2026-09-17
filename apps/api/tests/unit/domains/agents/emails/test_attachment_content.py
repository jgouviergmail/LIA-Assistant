"""Reading a mail attachment: its text when it has one, a vision reading otherwise.

The bytes of a downloaded attachment are classified by what they ARE (magic
bytes, the header as a fallback), extracted through the pipeline every
knowledge space already uses, and — for an image or a PDF without a text
layer — described by the vision slot under a page bound. What the tests pin:

- the route is decided on the bytes, never on the sender's word alone;
- the vision call rides the turn's config (the spend is the turn's), refuses
  a truncated answer (ADR-275) and steps aside under a ceiling refusal
  (``skipped_quota`` — never « failed »);
- the pages handed to the model are bounded and downscaled.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from PIL import Image

from src.domains.agents.emails import attachment_content as ac
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent

pytestmark = pytest.mark.unit


def _png(width: int = 64, height: int = 32) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 20, 20)).save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf(text: str | None) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    else:
        # A scanned page: an image, no text layer.
        page.insert_image(fitz.Rect(0, 0, 200, 100), stream=_png())
    return doc.tobytes()


def _docx(text: str) -> bytes:
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


# ============================================================================
# Classification on the bytes
# ============================================================================


def test_mime_is_read_from_the_bytes_before_the_header() -> None:
    assert ac.detect_mime(_png(), "application/octet-stream") == "image/png"
    assert ac.detect_mime(_pdf("x"), "text/plain") == "application/pdf"


def test_mime_falls_back_to_the_header_when_the_bytes_say_nothing() -> None:
    assert ac.detect_mime(b"plain words", "text/plain") == "text/plain"
    assert ac.detect_mime(b"plain words", "") == "application/octet-stream"


@pytest.mark.parametrize(
    ("mime", "route"),
    [
        ("application/pdf", ac.Route.TEXT),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ac.Route.TEXT),
        ("text/csv", ac.Route.TEXT),
        ("image/png", ac.Route.IMAGE),
        ("image/heic", ac.Route.IMAGE),
        ("application/zip", ac.Route.UNSUPPORTED),
        ("video/mp4", ac.Route.UNSUPPORTED),
    ],
)
def test_route_of_a_mime(mime: str, route: ac.Route) -> None:
    assert ac.route_of(mime) is route


# ============================================================================
# Text extraction through the knowledge-space pipeline
# ============================================================================


async def test_extracts_text_from_a_docx_and_a_pdf() -> None:
    assert "hello from word" in await ac.extract_text_from_bytes(
        _docx("hello from word"), ac.DOCX_MIME
    )
    assert "hello from pdf" in await ac.extract_text_from_bytes(
        _pdf("hello from pdf"), "application/pdf"
    )


async def test_a_scanned_pdf_has_no_text_and_is_recognised_as_such() -> None:
    data = _pdf(None)
    assert (await ac.extract_text_from_bytes(data, "application/pdf")).strip() == ""
    assert await ac.is_scanned_pdf(data) is True
    assert await ac.is_scanned_pdf(_pdf("words")) is False


# ============================================================================
# Pages for the vision model
# ============================================================================


async def test_an_image_is_downscaled_to_the_edge_bound() -> None:
    pages = (await ac.render_pages(_png(400, 200), "image/png", max_pages=4, max_edge=100)).pages
    assert len(pages) == 1
    with Image.open(io.BytesIO(pages[0])) as img:
        assert max(img.size) == 100


async def test_pdf_pages_are_bounded() -> None:
    import fitz

    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    data = doc.tobytes()
    pages = (await ac.render_pages(data, "application/pdf", max_pages=2, max_edge=400)).pages
    assert len(pages) == 2
    with Image.open(io.BytesIO(pages[0])) as img:
        assert img.format == "PNG"


async def test_a_giant_pdf_page_is_rasterised_under_a_pixel_bound() -> None:
    """The bound applies BEFORE the raster, not only to the PNG handed to the model.

    A page of 14 400 pt (200 inches) a side at the nominal render scale would
    allocate a 28 800 px square pixmap — gigabytes — before any downscale.
    """
    import fitz

    doc = fitz.open()
    doc.new_page(width=14_400, height=14_400)
    data = doc.tobytes()
    seen: list[tuple[int, int]] = []
    original = fitz.Page.get_pixmap

    def spy(page, *args, **kwargs):
        pixmap = original(page, *args, **kwargs)
        seen.append((pixmap.width, pixmap.height))
        return pixmap

    with patch.object(fitz.Page, "get_pixmap", spy):
        pages = (await ac.render_pages(data, "application/pdf", max_pages=1, max_edge=400)).pages
    assert len(pages) == 1
    assert max(seen[0]) <= 2 * 400


# ============================================================================
# The vision reading
# ============================================================================


def _fake_llm(text: str, *, truncated: bool = False) -> MagicMock:
    metadata = {"finish_reason": "length"} if truncated else {"finish_reason": "stop"}
    return AIMessage(content=text, response_metadata=metadata)


async def test_vision_reading_rides_the_turn_config_and_returns_the_text() -> None:
    invoke = AsyncMock(return_value=_fake_llm("An invoice of 120 EUR dated 3 May."))
    config = {"callbacks": ["tracker"]}
    with (
        patch.object(ac, "invoke_with_instrumentation", invoke),
        patch.object(ac, "get_llm", return_value=MagicMock()),
        patch.object(ac, "spend_blocked", AsyncMock(return_value=False)),
    ):
        reading = await ac.describe_with_vision(
            ac.RenderedPages([_png()], 1),
            question="what is it?",
            language="fr",
            user_id="u1",
            config=config,
        )
    assert reading.outcome == "ok"
    assert reading.text == "An invoice of 120 EUR dated 3 May."
    kwargs = invoke.await_args.kwargs
    assert kwargs["config"] is config and kwargs["user_id"] == "u1"
    message = kwargs["messages"][0]
    kinds = [block["type"] for block in message.content]
    assert kinds == ["text", "image_url"]
    assert "what is it?" in message.content[0]["text"]


async def test_vision_reading_refuses_a_truncated_answer() -> None:
    invoke = AsyncMock(return_value=_fake_llm("cut", truncated=True))
    with (
        patch.object(ac, "invoke_with_instrumentation", invoke),
        patch.object(ac, "get_llm", return_value=MagicMock()),
        patch.object(ac, "spend_blocked", AsyncMock(return_value=False)),
    ):
        reading = await ac.describe_with_vision(
            ac.RenderedPages([_png()], 1), question=None, language="en", user_id="u1", config=None
        )
    assert reading.outcome == "truncated"
    assert reading.text == ""


async def test_vision_reading_steps_aside_under_a_ceiling_refusal() -> None:
    invoke = AsyncMock()
    with (
        patch.object(ac, "invoke_with_instrumentation", invoke),
        patch.object(ac, "spend_blocked", AsyncMock(return_value=True)),
    ):
        reading = await ac.describe_with_vision(
            ac.RenderedPages([_png()], 1), question=None, language="en", user_id="u1", config=None
        )
    assert reading.outcome == "skipped_quota"
    invoke.assert_not_awaited()


# ============================================================================
# The orchestration: one attachment in, one reading out
# ============================================================================


async def test_read_attachment_serves_the_text_of_a_document() -> None:
    content = EmailAttachmentContent("notes.docx", ac.DOCX_MIME, _docx("the agenda for monday"))
    reading = await ac.read_attachment(
        content, question=None, language="en", user_id="u1", config=None, max_pages=4, max_edge=800
    )
    assert reading.route is ac.Route.TEXT
    assert reading.outcome == "ok"
    assert "the agenda for monday" in reading.text
    assert reading.mime_type == ac.DOCX_MIME


async def test_read_attachment_reads_a_scanned_pdf_with_the_vision_slot() -> None:
    content = EmailAttachmentContent("scan.pdf", "application/pdf", _pdf(None))
    vision = AsyncMock(return_value=ac.VisionReading(outcome="ok", text="A stamped receipt."))
    with patch.object(ac, "describe_with_vision", vision):
        reading = await ac.read_attachment(
            content,
            question="amount?",
            language="en",
            user_id="u1",
            config=None,
            max_pages=4,
            max_edge=800,
        )
    assert reading.route is ac.Route.VISION
    assert reading.text == "A stamped receipt."
    assert vision.await_args.kwargs["question"] == "amount?"


async def test_read_attachment_refuses_an_unsupported_type() -> None:
    content = EmailAttachmentContent("archive.zip", "application/zip", b"PK\x03\x04" + b"\x00" * 30)
    reading = await ac.read_attachment(
        content, question=None, language="en", user_id="u1", config=None, max_pages=4, max_edge=800
    )
    assert reading.route is ac.Route.UNSUPPORTED
    assert reading.outcome == "unsupported"


async def test_a_heic_attachment_is_a_picture_the_vision_slot_can_see() -> None:
    """An iPhone photo (HEIC) routes to vision and renders to a PNG page."""
    from src.infrastructure.media.heif import ensure_heif_support

    ensure_heif_support()
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 200)).save(buffer, format="HEIF")
    data = buffer.getvalue()

    mime = ac.detect_mime(data, "application/octet-stream")
    assert ac.route_of(mime) is ac.Route.IMAGE
    pages = (await ac.render_pages(data, mime, max_pages=1, max_edge=32)).pages
    with Image.open(io.BytesIO(pages[0])) as img:
        assert img.format == "PNG"
        assert max(img.size) <= 32


async def test_a_cut_page_set_is_stated_to_the_model_and_to_the_loop() -> None:
    """Six pages under a bound of two: the vision message says « 2 of 6 » so the
    model claims no completeness, and the reading carries both counts."""
    import fitz

    doc = fitz.open()
    for index in range(6):
        page = doc.new_page()
        page.insert_image(fitz.Rect(0, 0, 200, 100), stream=_png())
        del index
    content = EmailAttachmentContent("scan.pdf", "application/pdf", doc.tobytes())
    invoke = AsyncMock(return_value=_fake_llm("Page 1: a receipt. Page 2: a receipt."))
    with (
        patch.object(ac, "invoke_with_instrumentation", invoke),
        patch.object(ac, "get_llm", return_value=MagicMock()),
        patch.object(ac, "spend_blocked", AsyncMock(return_value=False)),
    ):
        reading = await ac.read_attachment(
            content,
            question=None,
            language="en",
            user_id="u1",
            config=None,
            max_pages=2,
            max_edge=200,
        )
    assert reading.route is ac.Route.VISION
    assert (reading.pages_read, reading.pages_total) == (2, 6)
    prompt = invoke.await_args.kwargs["messages"][0].content[0]["text"]
    assert "2" in prompt and "6" in prompt and "first 2" in prompt
    # A set shown whole says nothing about a cut.
    invoke.reset_mock()
    with (
        patch.object(ac, "invoke_with_instrumentation", invoke),
        patch.object(ac, "get_llm", return_value=MagicMock()),
        patch.object(ac, "spend_blocked", AsyncMock(return_value=False)),
    ):
        whole = await ac.read_attachment(
            content,
            question=None,
            language="en",
            user_id="u1",
            config=None,
            max_pages=8,
            max_edge=200,
        )
    assert (whole.pages_read, whole.pages_total) == (6, 6)
    assert "first 6" not in invoke.await_args.kwargs["messages"][0].content[0]["text"]
