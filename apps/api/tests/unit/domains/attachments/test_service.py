"""Tests for AttachmentService — CA-4 off-event-loop disk write.

The upload path writes the (potentially multi-MB) file bytes to disk. A raw
synchronous ``write_bytes`` on the async request path blocks the whole event
loop; the write must be offloaded via ``asyncio.to_thread``.
"""

import threading
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.attachments.models import AttachmentContentType
from src.domains.attachments.service import AttachmentService


@pytest.mark.unit
class TestAttachmentUploadOffEventLoop:
    """CA-4: the attachment disk write must not run on the event-loop thread."""

    @pytest.mark.asyncio
    async def test_upload_writes_off_event_loop(self, tmp_path) -> None:
        db = AsyncMock()
        service = AttachmentService(db)
        service.repo = AsyncMock()
        mock_attachment = MagicMock(id=uuid.uuid4())
        service.repo.create = AsyncMock(return_value=mock_attachment)

        # Stub the in-memory processing so the flow reaches the disk write with a
        # plain PNG and no HEIC/PDF branches.
        service._settings = MagicMock(
            attachments_storage_path=str(tmp_path), attachments_ttl_hours=24
        )
        service._detect_mime_type = MagicMock(return_value="image/png")
        service._classify_content = MagicMock(return_value=AttachmentContentType.IMAGE)
        service._get_max_size_bytes = MagicMock(return_value=10_000_000)
        service._mime_to_extension = MagicMock(return_value="png")

        png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        mock_file = MagicMock()
        mock_file.filename = "photo.png"
        mock_file.read = AsyncMock(return_value=png_bytes)

        main_tid = threading.get_ident()
        write_tid: dict[str, int] = {}
        real_write = Path.write_bytes

        def spy_write(self_path, data):
            write_tid["tid"] = threading.get_ident()
            return real_write(self_path, data)

        with patch("pathlib.Path.write_bytes", spy_write):
            result = await service.upload(uuid.uuid4(), mock_file)

        assert result is mock_attachment
        # Ran in a worker thread, not the event-loop thread.
        assert write_tid["tid"] != main_tid
        # Behavior preserved: the file is physically written to disk.
        written = list(tmp_path.rglob("*.png"))
        assert written and written[0].read_bytes() == png_bytes
