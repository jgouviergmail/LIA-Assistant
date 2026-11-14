"""Generated image publication writes bytes off-loop under its recorded account path."""

import threading
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.file_contracts import UploadMetadata
from src.domains.attachments.generated_publication import publish_generated_files
from src.domains.attachments.models import AttachmentOrigin
from tests.helpers.attachment_publication import stub_publication

pytestmark = pytest.mark.unit


async def test_write_image_file_off_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"y" * 48
    main_thread = threading.get_ident()
    writes: list[int] = []
    original = Path.write_bytes

    def observed(path: Path, data: bytes) -> int:
        writes.append(threading.get_ident())
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", observed)
    metadata = UploadMetadata(
        "image.png", "image/png", "image", ".png", AttachmentOrigin.GENERATED_IMAGE
    )
    with stub_publication(tmp_path):
        rows = await publish_generated_files(
            AsyncMock(spec=AsyncSession), owner_id=uuid4(), files=[(metadata, png)]
        )
    assert len(writes) == 1 and writes[0] != main_thread
    assert (tmp_path / rows[0].file_path).read_bytes() == png
