"""Uploads join exact approval transactions without losing bytes on uncertain commit ACK."""

import asyncio
import threading
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import select

from src.core.config import settings
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("failure", ["disk", "cancel", "short"])
async def test_failed_file_worker_finishes_and_removes_orphan_before_upload_returns(
    async_session, test_user, monkeypatch, tmp_path: Path, failure
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Interrupted uploads")
    async_session.add(space)
    await async_session.commit()
    space_id = space.id
    started, release = threading.Event(), threading.Event()
    original_write = Path.write_bytes

    def interrupted(path, content):
        started.set()
        if failure == "cancel":
            assert release.wait(5)
        original_write(path, content[:2])
        if failure == "disk":
            raise OSError("Controlled disk failure")
        return len(content[:2])

    monkeypatch.setattr(Path, "write_bytes", interrupted)
    operation = asyncio.create_task(
        RAGSpaceService(async_session).upload_document(
            space_id,
            owner,
            UploadFile(filename="controlled.txt", file=BytesIO(b"data")),
            commit=False,
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 5)
        if failure == "cancel":
            operation.cancel()
            await asyncio.sleep(0.02)
            assert not operation.done()
            operation.cancel()
            await asyncio.sleep(0.02)
            assert not operation.done()
        release.set()
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else OSError):
            await operation
    finally:
        release.set()
        await asyncio.gather(operation, return_exceptions=True)
    await async_session.rollback()
    assert not list(tmp_path.rglob("*.txt"))
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.space_id == space_id))
        is None
    )


async def test_source_upload_can_defer_commit_and_preserves_bytes_through_rollback(
    async_session, test_user, monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Approved uploads")
    async_session.add(space)
    await async_session.commit()
    space_id = space.id
    chosen_id = uuid4()
    document = await RAGSpaceService(async_session).upload_document(
        space_id,
        owner,
        UploadFile(filename="controlled.txt", file=BytesIO(b"data")),
        commit=False,
        document_id=chosen_id,
    )
    identity, filename = document.id, document.filename
    assert identity == chosen_id
    path = tmp_path / str(owner) / str(space_id) / filename
    assert document.status == "pending" and path.read_bytes() == b"data"
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == identity))
        == identity
    )
    await async_session.rollback()
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == identity)) is None
    )
    # The caller owns cleanup after verified rollback; source never deletes
    # bytes merely because it failed to receive a commit acknowledgement.
    assert path.read_bytes() == b"data"


@pytest.mark.parametrize("cancelled", [False, True])
async def test_source_upload_lost_commit_ack_keeps_the_real_committed_document_file(
    async_session, test_user, monkeypatch, tmp_path: Path, cancelled
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Unknown uploads")
    async_session.add(space)
    await async_session.commit()
    space_id = space.id
    original_commit = async_session.commit

    async def lost():
        await original_commit()
        if cancelled:
            raise asyncio.CancelledError()
        raise OSError("Controlled lost commit acknowledgement")

    monkeypatch.setattr(async_session, "commit", lost)
    with pytest.raises((OSError, asyncio.CancelledError)):
        await RAGSpaceService(async_session).upload_document(
            space_id, owner, UploadFile(filename="controlled.txt", file=BytesIO(b"data"))
        )
    await async_session.rollback()
    document = await async_session.scalar(
        select(RAGDocument).where(RAGDocument.space_id == space_id)
    )
    assert document is not None
    assert (tmp_path / str(owner) / str(space_id) / document.filename).read_bytes() == b"data"
