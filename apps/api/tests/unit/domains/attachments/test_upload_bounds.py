"""A multipart body and its converted image are bounded before destination effects."""

import io
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from src.core.config import settings
from src.core.constants import ATTACHMENTS_READ_CHUNK_BYTES
from src.core.exceptions import BaseAPIException
from src.domains.attachments.service import AttachmentService
from tests.helpers.attachment_publication import stub_publication

pytestmark = pytest.mark.unit


class ObservedUpload(UploadFile):
    """Use a real spool, recording the bytes actually requested and retained."""

    def __init__(self, body: bytes) -> None:
        super().__init__(file=io.BytesIO(body), filename="fixture.png")
        self.read_sizes: list[int] = []
        self.consumed = 0

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        content = await super().read(size)
        self.consumed += len(content)
        return content


async def test_rejected_body_stops_at_the_first_excess_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "attachments_max_image_size_mb", 1)
    limit = settings.attachments_max_image_size_mb * 1024 * 1024
    upload = ObservedUpload(b"\x89PNG\r\n\x1a\n" + b"x" * (limit * 2))
    try:
        with stub_publication(tmp_path) as writer, pytest.raises(BaseAPIException) as refused:
            await AttachmentService(AsyncMock()).upload(uuid4(), upload)
        assert refused.value.status_code == 413
        assert upload.consumed == limit + 1
        assert all(0 < size <= ATTACHMENTS_READ_CHUNK_BYTES for size in upload.read_sizes)
        assert writer.rows == {} and list(tmp_path.iterdir()) == []
    finally:
        await upload.close()


async def test_conversion_cannot_bypass_the_image_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "attachments_max_image_size_mb", 1)
    limit = settings.attachments_max_image_size_mb * 1024 * 1024
    service = AttachmentService(AsyncMock())
    monkeypatch.setattr(service, "_detect_mime_type", lambda _: "image/heic")
    monkeypatch.setattr(
        service, "_convert_heic_to_jpeg", lambda _: (b"x" * (limit + 1), "image/jpeg")
    )
    upload = ObservedUpload(b"small compressed fixture")
    try:
        with stub_publication(tmp_path) as writer, pytest.raises(BaseAPIException) as refused:
            await service.upload(uuid4(), upload)
        assert refused.value.status_code == 413
        assert writer.rows == {} and list(tmp_path.iterdir()) == []
    finally:
        await upload.close()
