"""Real SQL selections are constant-query, private, exact and fail closed before ZIP transfer."""

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import event

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceConflictError
from src.domains.rag_spaces import document_archives
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.users.models import User
from src.infrastructure.file_transfer import LocalFileRead

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "metadata_changed",
        "missing_appeared",
        "foreign",
        "system",
        "ceiling",
        "write_failed",
        "copy_cancelled",
        "cleanup_cancelled",
    ],
)
async def test_archive_selection_is_owned_exact_bounded_and_closes_files(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, foreign = test_user.id, uuid4()
    async_session.add(User(id=foreign, email=f"archive-{foreign}@example.test", is_active=True))
    space = RAGSpace(user_id=owner, name="Personal archive", is_system=scenario == "system")
    async_session.add(space)
    await async_session.flush()
    documents = [
        RAGDocument(
            user_id=foreign if scenario == "foreign" and index == 0 else owner,
            space_id=space.id,
            filename=f"{index}.txt",
            original_filename=name,
            file_size=4,
            content_type="text/plain",
            status="ready",
        )
        for index, name in enumerate(["../report.txt", "REPORT.TXT", "lost\n.txt"])
    ]
    async_session.add_all(documents)
    await async_session.commit()
    space_id, ids = space.id, tuple(document.id for document in documents)
    directory = tmp_path / str(owner) / str(space_id)
    directory.mkdir(parents=True)
    for index in range(2):
        (directory / f"{index}.txt").write_bytes(b"data")
    if scenario == "ceiling":
        monkeypatch.setattr(settings, "rag_spaces_archive_max_mb", 0)
    selects = []

    def record_sql(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    engine = async_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        if scenario in {"foreign", "system", "ceiling"}:
            with pytest.raises(BaseAPIException):
                await document_archives.read_owned_archive_snapshot(
                    async_session, owner, space_id, ids
                )
            return
        with patch.object(
            document_archives.zipfile, "ZipFile", side_effect=AssertionError("ZIP before consent")
        ):
            selected = await document_archives.read_owned_archive_snapshot(
                async_session, owner, space_id, ids
            )
        assert len(selects) == 2
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)
    public = selected.public_scope()
    assert "file_digest" not in str(public) and "source_digest" not in str(public)
    assert str(tmp_path) not in str(selected.model_dump(mode="json"))
    assert [document.member_name for document in selected.documents] == [
        "report.txt",
        "REPORT (2).TXT",
        "lost_.txt",
    ]
    assert [document.present for document in selected.documents] == [True, True, False]
    if scenario == "metadata_changed":
        documents[0].error_message = "private new support detail"
        await async_session.commit()
    elif scenario == "missing_appeared":
        (directory / "2.txt").write_bytes(b"data")
    if scenario in {"metadata_changed", "missing_appeared"}:
        with pytest.raises(ResourceConflictError):
            await document_archives.open_owned_document_archive(async_session, owner, selected)
        return
    opened = []
    original = LocalFileRead.open

    def capture(path):
        reader = original(path)
        opened.append(reader)
        return reader

    monkeypatch.setattr(LocalFileRead, "open", capture)
    if scenario in {"write_failed", "copy_cancelled", "cleanup_cancelled"}:
        failure = (
            OSError("controlled disk failure")
            if scenario == "write_failed"
            else asyncio.CancelledError()
        )
        monkeypatch.setattr(LocalFileRead, "copy_to", AsyncMock(side_effect=failure))
        if scenario == "cleanup_cancelled":
            original_close = LocalFileRead.close

            async def interrupted_close(reader):
                await original_close(reader)
                if reader is opened[0]:
                    raise asyncio.CancelledError()

            monkeypatch.setattr(LocalFileRead, "close", interrupted_close)
            failure = asyncio.CancelledError()
        with pytest.raises(type(failure)):
            await document_archives.open_owned_document_archive(async_session, owner, selected)
        assert opened and all(reader.closed for reader in opened)
        return
    reader = await document_archives.open_owned_document_archive(async_session, owner, selected)
    try:
        assert all(source.closed for source in opened)
        chunks = []
        while chunk := await reader.read_chunk():
            chunks.append(chunk)
        with ZipFile(BytesIO(b"".join(chunks))) as archive:
            assert archive.namelist() == ["report.txt", "REPORT (2).TXT", "_missing.txt"]
            assert archive.read("report.txt") == archive.read("REPORT (2).TXT") == b"data"
            assert archive.read("_missing.txt") == b"lost_.txt\n"
    finally:
        await reader.close()
