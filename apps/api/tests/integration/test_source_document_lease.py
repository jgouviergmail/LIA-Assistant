"""A live source does not let an expired/replaced document job publish chunks."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from src.core.config import settings
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.source_document_lease import require_source_document
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    source_worker_scope,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario", ["valid", "expired", "taken_over", "completed", "unlinked", "foreign_owner"]
)
async def test_source_document_requires_its_own_live_job_before_commit(
    async_session, test_user, monkeypatch, kind, scenario
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
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    keys = (
        {"folder_id": "root", "folder_name": "Root"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Label"}
    )
    token = f"native-{uuid4()}"
    source = model(user_id=owner, space_id=space_id, worker_id=token, sync_status="syncing", **keys)
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    reference = "drive_source_id" if kind == "drive" else "mail_source_id"
    document = RAGDocument(
        user_id=owner,
        space_id=space_id,
        filename="doc.txt",
        original_filename="doc.txt",
        content_type="text/plain",
        file_size=1,
        status="processing",
        worker_id="doc-owner",
        **{reference: source_id},
    )
    async_session.add(document)
    await async_session.flush()
    document_id = document.id
    await async_session.execute(
        text(
            f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    await async_session.execute(
        text(
            "UPDATE rag_documents SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(document_id)},
    )
    changes = {
        "expired": "lease_expires_at = clock_timestamp() - interval '1 second'",
        "taken_over": "worker_id = 'another-job'",
        "completed": "status = 'ready'",
        "unlinked": f"{reference} = NULL",
        "foreign_owner": "user_id = NULL",
    }
    if scenario != "valid":
        await async_session.execute(
            text(f"UPDATE rag_documents SET {changes[scenario]} WHERE id = :id"),
            {"id": str(document_id)},
        )
    await async_session.commit()
    scope = SourceWorkerLease(kind, source_id, space_id, owner, token)
    with source_worker_scope(scope):
        if scenario == "valid":
            await require_source_document(async_session, document_id, "doc-owner")
        else:
            with pytest.raises(SourceLeaseLost):
                await require_source_document(async_session, document_id, "doc-owner")
