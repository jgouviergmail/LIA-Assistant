"""The shared image's file checks are whole disk calls, run in a worker thread (AC-035).

Resolving the stored image's path was done on the event loop before its digest
was handed to a thread, and so was the check that the recipient's gallery row
points to the copied file. Each is now one synchronous helper the action runs
through ``asyncio.to_thread``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.application import peer_image
from src.domains.attachments.models import Attachment

pytestmark = pytest.mark.unit

IMAGE = b"\x89PNG proof image"


@pytest.fixture
def stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Attachment, Path]:
    """A gallery row and the file it names under the attachments root."""
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    relative = f"{uuid4()}/image.png"
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_bytes(IMAGE)
    return Attachment(id=uuid4(), file_path=relative), path


def test_the_source_digest_is_the_stored_file_digest(stored: tuple[Attachment, Path]) -> None:
    row, _ = stored

    assert peer_image._source_digest(row) == hashlib.sha256(IMAGE).hexdigest()


def test_a_gallery_row_names_the_copy_it_points_to(
    stored: tuple[Attachment, Path], tmp_path: Path
) -> None:
    row, path = stored

    assert peer_image._names_the_copy(row, path)
    assert not peer_image._names_the_copy(row, tmp_path / "another.png")
