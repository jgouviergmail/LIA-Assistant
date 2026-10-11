"""A real SQL preflight reads currentness at constant query count and releases provider waits."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncEngine

from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus, RAGDriveSource, RAGSpace
from src.domains.rag_spaces.repository import RAGDocumentRepository
from tests.unit.domains.rag_spaces.drive_fakes import FakeDriveClient, drive_file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "status",
    [
        RAGDocumentStatus.READY,
        RAGDocumentStatus.PENDING,
        RAGDocumentStatus.PROCESSING,
        RAGDocumentStatus.ERROR,
        RAGDocumentStatus.REINDEXING,
    ],
)
async def test_preflight_uses_two_document_queries_and_no_transaction_during_drive(
    async_session, test_user, monkeypatch, status
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    source = RAGDriveSource(user_id=owner, space_id=space_id, folder_id="root", folder_name="Root")
    async_session.add(source)
    async_session.add(
        RAGDocument(
            user_id=owner,
            space_id=space_id,
            filename="f.pdf",
            original_filename="f.pdf",
            file_size=1,
            content_type="application/pdf",
            status=status,
            drive_file_id="same",
            drive_modified_time=datetime(2026, 9, 17, 10, tzinfo=UTC),
        )
    )
    await async_session.commit()
    source_id = source.id
    client = FakeDriveClient(
        {"root": [drive_file("same")] + [drive_file(f"new-{index}") for index in range(20)]}
    )
    original = client.list_files

    async def no_transaction(**kwargs):
        assert not async_session.in_transaction()
        return await original(**kwargs)

    monkeypatch.setattr(client, "list_files", no_transaction)

    async def get_client(self, actor):
        assert actor == owner
        return client

    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", get_client)

    @asynccontextmanager
    async def database():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    binding = async_session.bind
    engine = binding.sync_engine if isinstance(binding, AsyncEngine) else binding.engine.sync_engine
    statements = []

    def counted(connection, cursor, statement, parameters, context, executemany):
        if "FROM rag_documents" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", counted)
    try:
        result = await RAGDriveSyncService(async_session).preflight(space_id, source_id, owner)
    finally:
        event.remove(engine, "before_cursor_execute", counted)
    assert result.unchanged == (1 if status == RAGDocumentStatus.READY else 0)
    assert result.modified == (0 if status == RAGDocumentStatus.READY else 1)
    assert result.new == 20
    assert len(statements) == 2


async def test_batched_currentness_refuses_ambiguous_identity_within_the_space(
    async_session, test_user
):
    space = RAGSpace(user_id=test_user.id, name="Ambiguous documents")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    for index in range(2):
        async_session.add(
            RAGDocument(
                user_id=test_user.id,
                space_id=space_id,
                filename=f"{index}.pdf",
                original_filename=f"{index}.pdf",
                file_size=1,
                content_type="application/pdf",
                drive_file_id="duplicate",
            )
        )
    await async_session.flush()
    repository = RAGDocumentRepository(async_session)
    with pytest.raises(MultipleResultsFound):
        await repository.get_by_drive_file_ids(space_id, ["duplicate"])
