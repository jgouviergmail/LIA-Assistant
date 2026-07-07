"""CA-4: generated-image disk write must run off the event-loop thread.

``generate_image`` / ``edit_image`` persist a freshly generated PNG (up to a
few MB) to disk. The write is offloaded via ``_write_image_file`` so it never
blocks the event loop during a generation.
"""

import threading
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.tools import image_generation_tools


@pytest.mark.unit
@pytest.mark.asyncio
async def test_write_image_file_off_event_loop(tmp_path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"y" * 48
    relative_path = f"{uuid.uuid4()}/img.png"

    main_tid = threading.get_ident()
    write_tid: dict[str, int] = {}
    real_write = Path.write_bytes

    def spy_write(self_path, data):
        write_tid["tid"] = threading.get_ident()
        return real_write(self_path, data)

    fake_settings = MagicMock(attachments_storage_path=str(tmp_path))
    with (
        patch.object(image_generation_tools, "settings", fake_settings),
        patch("pathlib.Path.write_bytes", spy_write),
    ):
        path = await image_generation_tools._write_image_file(png, relative_path)

    # Ran in a worker thread, not the event-loop thread.
    assert write_tid["tid"] != main_tid
    # Behavior preserved: bytes physically written to the resolved path.
    assert path == Path(tmp_path) / relative_path
    assert path.read_bytes() == png
