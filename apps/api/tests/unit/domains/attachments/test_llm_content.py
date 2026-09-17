"""Tests for attachments.llm_content vision-message building — CA-4.

``build_vision_message`` loads attachment images from disk and base64-encodes
them just before the LLM call, on the response hot path. The blocking disk
reads must be offloaded via the async wrapper ``build_vision_message_async``.
"""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from src.domains.attachments.llm_content import (
    build_vision_message,
    build_vision_message_async,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 32


def _image_attachment() -> dict:
    return {
        "id": "att-1",
        "content_type": "image",
        "file_path": "u/img.png",
        "mime_type": "image/png",
    }


@pytest.mark.unit
class TestBuildVisionMessage:
    """Behavior + off-event-loop guarantee for vision message building."""

    def test_build_vision_message_embeds_base64_image(self, tmp_path) -> None:
        img = tmp_path / "u" / "img.png"
        img.parent.mkdir(parents=True)
        img.write_bytes(_PNG)

        msg = build_vision_message("look", [_image_attachment()], str(tmp_path))

        assert isinstance(msg.content, list)
        blocks = [b for b in msg.content if isinstance(b, dict)]
        assert any(b.get("type") == "image_url" for b in blocks)
        assert any(b.get("type") == "text" and b.get("text") == "look" for b in blocks)

    @pytest.mark.asyncio
    async def test_build_vision_message_async_reads_off_event_loop(self, tmp_path) -> None:
        img = tmp_path / "u" / "img.png"
        img.parent.mkdir(parents=True)
        img.write_bytes(_PNG)

        main_tid = threading.get_ident()
        read_tid: dict[str, int] = {}
        real_read = Path.read_bytes

        def spy_read(self_path):
            read_tid["tid"] = threading.get_ident()
            return real_read(self_path)

        with patch("pathlib.Path.read_bytes", spy_read):
            msg = await build_vision_message_async("look", [_image_attachment()], str(tmp_path))

        # Ran in a worker thread, not the event-loop thread.
        assert read_tid["tid"] != main_tid
        # Behavior preserved: base64 image block present.
        blocks = [b for b in msg.content if isinstance(b, dict)]
        assert any(b.get("type") == "image_url" for b in blocks)


@pytest.mark.unit
class TestAttachmentHintAndDocumentBlock:
    """The hint speaks the reader's language through the central tables; a cut is stated."""

    def test_the_hint_is_translated_through_the_backend_canonical_code(self) -> None:
        from src.domains.attachments.llm_content import build_attachment_hint

        atts = [{"content_type": "document", "original_filename": "notes.docx", "mime_type": "x"}]
        # `zh` reaches the backend as the frontend spells it; the table is keyed zh-CN.
        assert "附件" in build_attachment_hint(atts, user_language="zh")
        assert "附件" in build_attachment_hint(atts, user_language="zh-CN")
        assert "Pièce jointe" in build_attachment_hint(atts, user_language="fr-FR")
        assert "Anhang" in build_attachment_hint(atts, user_language="de")

    def test_a_capped_text_states_its_cut_to_the_model(self) -> None:
        from src.domains.attachments.llm_content import build_vision_message

        cap = 1000
        with patch("src.domains.attachments.llm_content.settings") as settings_mock:
            settings_mock.attachments_max_pdf_text_chars = cap
            message = build_vision_message(
                "summarise it",
                [
                    {
                        "id": "a1",
                        "content_type": "document",
                        "original_filename": "long.pdf",
                        "mime_type": "application/pdf",
                        "file_path": "u/long.pdf",
                        "extracted_text": "x" * cap,
                    },
                    {
                        "id": "a2",
                        "content_type": "document",
                        "original_filename": "short.pdf",
                        "mime_type": "application/pdf",
                        "file_path": "u/short.pdf",
                        "extracted_text": "short",
                    },
                ],
                storage_path="/nowhere",
            )
        blocks = [b["text"] for b in message.content if b["type"] == "text"]
        long_block = next(b for b in blocks if "long.pdf" in b)
        short_block = next(b for b in blocks if "short.pdf" in b)
        assert f"first {cap} characters" in long_block
        assert "characters" not in short_block
