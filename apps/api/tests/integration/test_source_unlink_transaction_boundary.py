"""Retaining documents while unlinking joins the caller's approval transaction."""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDriveSource,
    RAGMailSource,
    RAGSpace,
)
from src.domains.rag_spaces.storage_paths import stored_file_path

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize("destructive", [False, True])
async def test_source_unlink_deferred_retains_rows_and_file_and_can_roll_back(
    async_session, test_user, tmp_path, monkeypatch, kind, destructive
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    if kind == "drive":
        source = RAGDriveSource(
            space_id=space_id, user_id=owner, folder_id="real-folder", folder_name="Folder"
        )
        service = RAGDriveSyncService(async_session)
        unlink = service.unlink_folder
        reference = RAGDocument.drive_source_id
        metric = "src.domains.rag_spaces.drive_sync.rag_drive_sources_total_count"
    else:
        source = RAGMailSource(
            space_id=space_id, user_id=owner, label_id="Label_1", label_name="Label"
        )
        service = RAGMailSyncService(async_session)
        unlink = service.unlink_label
        reference = RAGDocument.mail_source_id
        metric = "src.domains.rag_spaces.mail_source_service.rag_mail_sources_total_count"
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    document = RAGDocument(
        space_id=space_id,
        user_id=owner,
        filename="f.txt",
        original_filename="f.txt",
        content_type="text/plain",
        file_size=4,
        source_type=kind,
        **{reference.key: source_id},
    )
    async_session.add(document)
    await async_session.flush()
    document_id = document.id
    chunk = RAGChunk(
        document_id=document_id,
        space_id=space_id,
        user_id=owner,
        chunk_index=0,
        content="Controlled chunk",
        embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
        embedding_model="controlled",
    )
    async_session.add(chunk)
    await async_session.commit()
    chunk_id = chunk.id
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    file = stored_file_path(owner, space_id, "f.txt")
    file.parent.mkdir(parents=True)
    file.write_bytes(b"data")
    with patch(metric) as gauge:
        if destructive:
            with pytest.raises(ValueError):
                await unlink(space_id, source_id, owner, delete_documents=True, commit=False)
        else:
            await unlink(space_id, source_id, owner, delete_documents=False, commit=False)
            assert (
                await async_session.scalar(
                    select(type(source).id).where(type(source).id == source_id)
                )
                is None
            )
            assert (
                await async_session.scalar(select(reference).where(RAGDocument.id == document_id))
                is None
            )
            await async_session.rollback()
        gauge.dec.assert_not_called()
    assert (
        await async_session.scalar(select(type(source).id).where(type(source).id == source_id))
        == source_id
    )
    assert (
        await async_session.scalar(select(reference).where(RAGDocument.id == document_id))
        == source_id
    )
    assert file.read_bytes() == b"data"
    assert (
        await async_session.scalar(select(RAGChunk.id).where(RAGChunk.id == chunk_id)) == chunk_id
    )
