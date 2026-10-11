"""The actual native embedding pipeline refuses stale document/source results."""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from src.core.config import settings
from src.domains.rag_spaces import processing, source_document_lease, source_worker_runtime
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDriveSource, RAGSpace
from src.domains.rag_spaces.source_worker_lease import (
    SourceWorkerLease,
    current_source_worker,
    source_worker_scope,
)
from src.domains.rag_spaces.storage_paths import stored_file_path

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "document_expired",
        "document_takeover",
        "source_takeover",
        "disabled",
        "cancelled",
        "provider_failed",
    ],
)
async def test_native_processing_never_publishes_after_its_claim_is_lost(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_mail_sync_enabled",
        "rag_spaces_drive_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    token = f"native-{uuid4()}"
    source = RAGDriveSource(
        user_id=owner,
        space_id=space_id,
        worker_id=token,
        sync_status="syncing",
        folder_id="root",
        folder_name="Root",
    )
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    document = RAGDocument(
        user_id=owner,
        space_id=space_id,
        drive_source_id=source_id,
        filename="doc.txt",
        original_filename="doc.txt",
        content_type="text/plain",
        file_size=28,
        status="pending",
    )
    async_session.add(document)
    await async_session.flush()
    document_id = document.id
    await async_session.execute(
        text(
            "UPDATE rag_drive_sources SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    await async_session.commit()
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    path = stored_file_path(owner, space_id, "doc.txt")
    path.parent.mkdir(parents=True)
    path.write_text("Controlled document contents.", encoding="utf-8")

    @asynccontextmanager
    async def context():
        yield async_session

    for module in (processing, source_document_lease, source_worker_runtime):
        monkeypatch.setattr(module, "get_db_context", context)

    class Embeddings:
        model_name = settings.rag_spaces_embedding_model.removeprefix("models/")

        async def aembed_documents(self, texts):
            assert not async_session.in_transaction()
            if scenario == "document_expired":
                await async_session.execute(
                    text(
                        "UPDATE rag_documents SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
                    ),
                    {"id": str(document_id)},
                )
            elif scenario == "document_takeover":
                await async_session.execute(
                    text(
                        "UPDATE rag_documents SET worker_id = 'new-document-worker' WHERE id = :id"
                    ),
                    {"id": str(document_id)},
                )
            elif scenario == "source_takeover":
                await async_session.execute(
                    text(
                        "UPDATE rag_drive_sources SET worker_id = 'new-source-worker' WHERE id = :id"
                    ),
                    {"id": str(source_id)},
                )
            elif scenario == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            await async_session.commit()
            if scenario == "cancelled":
                raise asyncio.CancelledError()
            if scenario == "provider_failed":
                raise OSError("controlled provider failure")
            return [[0.001] * settings.rag_spaces_embedding_dimensions for _ in texts]

    monkeypatch.setattr(processing, "get_rag_embeddings", Embeddings)
    lease = SourceWorkerLease("drive", source_id, space_id, owner, token)
    with source_worker_scope(lease):
        call = processing.process_document(
            document_id, space_id, owner, "doc.txt", "doc.txt", "text/plain"
        )
        if scenario == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await call
        else:
            assert await call is (scenario == "valid")
    assert current_source_worker() is None
    await async_session.rollback()
    current = await async_session.scalar(
        select(RAGDocument)
        .where(RAGDocument.id == document_id)
        .execution_options(populate_existing=True)
    )
    assert current.status == (
        "ready"
        if scenario == "valid"
        else "error" if scenario == "provider_failed" else "processing"
    )
    count = await async_session.scalar(
        select(func.count(RAGChunk.id)).where(RAGChunk.document_id == document_id)
    )
    assert (count > 0) is (scenario == "valid")
    assert path.exists()
    if scenario == "document_takeover":
        assert current.worker_id == "new-document-worker"
