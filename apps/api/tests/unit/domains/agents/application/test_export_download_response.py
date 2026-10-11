"""The HTTP response owns and closes an archive reader on success or send failure."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.application.export_download_response import ExportDownloadResponse
from src.infrastructure.account_export_downloads import ExportArchiveSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("send_failure", [False, True])
async def test_binary_response_closes_its_reader_on_every_exit(send_failure: bool) -> None:
    now = datetime.now(UTC)
    reader = AsyncMock()
    reader.snapshot = ExportArchiveSnapshot(
        job_id=uuid4(),
        created_at=now,
        completed_at=None,
        expires_at=now + timedelta(minutes=5),
        file_size_bytes=4,
        archive_digest="a" * 64,
    )
    reader.read_chunk.side_effect = [b"data", b""]
    response = ExportDownloadResponse(reader)
    messages: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        if send_failure:
            raise OSError("simulated response connection failure")
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "asgi": {"spec_version": "2.4"}}
    if send_failure:
        with pytest.raises(Exception):
            await response(scope, receive, send)
    else:
        await response(scope, receive, send)
        assert (
            b"".join(
                message["body"] for message in messages if message["type"] == "http.response.body"
            )
            == b"data"
        )
        assert (
            response.headers["Content-Disposition"]
            == 'attachment; filename="lia-account-export.zip"'
        )
        assert response.headers["Cache-Control"] == "no-store"
    reader.close.assert_awaited_once()
