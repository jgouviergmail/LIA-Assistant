"""Approved native file/capacity limits refuse before bytes or rows are added."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from src.core.config import settings
from src.domains.rag_spaces.drive_ingest import create_pending_document
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGSpace
from src.domains.rag_spaces.source_worker_lease import SourceWorkerLease, source_worker_scope

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["approved_file", "approved_capacity", "lower_current_capacity"]
)
async def test_native_source_capacity_is_the_smaller_of_current_and_approved(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_drive_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    token = f"native-{uuid4()}"
    source = RAGDriveSource(
        user_id=owner,
        space_id=space_id,
        folder_id="root",
        folder_name="Root",
        worker_id=token,
        sync_status="syncing",
    )
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    await async_session.execute(
        text(
            "UPDATE rag_drive_sources SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    if scenario != "approved_file":
        async_session.add(
            RAGDocument(
                user_id=owner,
                space_id=space_id,
                filename="retained.txt",
                original_filename="retained.txt",
                content_type="text/plain",
                file_size=3,
                status="ready",
            )
        )
    if scenario == "lower_current_capacity":
        monkeypatch.setattr(settings, "rag_spaces_max_docs_per_space", 1)
    await async_session.commit()
    lease = SourceWorkerLease(
        "drive",
        source_id,
        space_id,
        owner,
        token,
        provider_id="root",
        max_file_bytes=3 if scenario == "approved_file" else 10,
        max_documents=2 if scenario == "lower_current_capacity" else 1,
    )
    with source_worker_scope(lease), pytest.raises(RuntimeError):
        await create_pending_document(
            async_session,
            space_id=space_id,
            user_id=owner,
            content=b"four",
            extension=".txt",
            original_name="doc.txt",
            content_type="text/plain",
            source_fields={"drive_source_id": source_id, "drive_file_id": "remote"},
        )
    await async_session.rollback()
    count = await async_session.scalar(
        select(func.count(RAGDocument.id)).where(RAGDocument.space_id == space_id)
    )
    assert count == int(scenario != "approved_file")
    assert not list(tmp_path.rglob("*.txt"))
