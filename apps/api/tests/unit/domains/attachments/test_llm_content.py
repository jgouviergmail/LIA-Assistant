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
