"""A file kept in a knowledge space from the Tools (ADR-372, lot 5).

The bytes are read through the Tools' own doors, before any session opens; the space's own upload
judges them; the indexing starts as an upload's does. Nothing here calls a model: the indexing's
spend stays on the road it already takes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.domains.tool_assists import keeping
from src.domains.tool_assists.keeping import keep_attachment, keep_file
from src.domains.workbench.schemas.mail import AttachmentRequest

pytestmark = pytest.mark.unit

PERSON = uuid4()
SPACE = uuid4()
DOCUMENT = SimpleNamespace(
    id=uuid4(), filename="stored.pdf", original_filename="Plan.pdf", content_type="application/pdf"
)


@dataclass
class _Bytes:
    data: bytes
    filename: str
    mime_type: str


@pytest.fixture
def uploads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What reached the space, a session open only around it."""
    seen: list[dict[str, Any]] = []
    sessions: list[str] = []

    class _Service:
        def __init__(self, db: object) -> None:
            sessions.append("open")

        async def upload_document(
            self, space_id: UUID, user_id: UUID, file: Any
        ) -> SimpleNamespace:
            seen.append(
                {
                    "space_id": space_id,
                    "user_id": user_id,
                    "name": file.filename,
                    "type": file.content_type,
                    "bytes": await file.read(),
                }
            )
            return DOCUMENT

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    started: list[str] = []

    async def process(**fields: Any) -> None:
        started.append(fields["original_filename"])

    def forget(work: Coroutine[Any, Any, None], name: str) -> None:
        work.close()
        started.append(name)

    monkeypatch.setattr(keeping, "RAGSpaceService", _Service)
    monkeypatch.setattr(keeping, "get_db_context", session)
    monkeypatch.setattr(keeping, "process_document", process)
    monkeypatch.setattr(keeping, "safe_fire_and_forget", forget)
    seen.append({"started": started})
    return seen


async def test_a_drive_file_reaches_the_space_as_an_upload_would(
    uploads: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def download(user_id: UUID, query: Any) -> _Bytes:
        assert user_id == PERSON
        assert query.id == "f1"
        return _Bytes(b"%PDF", "Plan.pdf", "application/pdf")

    monkeypatch.setattr(keeping, "download_file", download)

    document_id = await keep_file(PERSON, SPACE, "f1")

    assert document_id == DOCUMENT.id
    started, upload = uploads
    assert upload["space_id"] == SPACE
    assert upload["user_id"] == PERSON
    assert upload["name"] == "Plan.pdf"
    assert upload["type"] == "application/pdf"
    assert upload["bytes"] == b"%PDF"
    assert started["started"] == [f"rag_process_{DOCUMENT.id}"]


async def test_an_attachment_keeps_the_name_the_message_gave_it(
    uploads: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    request = AttachmentRequest(message_id="m1", attachment_id="a1", filename="Plan.pdf")

    async def download(user_id: UUID, asked: AttachmentRequest) -> _Bytes:
        assert asked is request
        return _Bytes(b"%PDF", "", "application/pdf")

    monkeypatch.setattr(keeping, "download_attachment", download)

    await keep_attachment(PERSON, SPACE, request)

    assert uploads[1]["name"] == "Plan.pdf"


async def test_a_refused_read_keeps_nothing(
    uploads: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def lost(user_id: UUID, query: Any) -> _Bytes:
        raise ConnectionError("the drive did not answer")

    monkeypatch.setattr(keeping, "download_file", lost)

    with pytest.raises(ConnectionError):
        await keep_file(PERSON, SPACE, "f1")

    assert len(uploads) == 1
    assert uploads[0]["started"] == []
