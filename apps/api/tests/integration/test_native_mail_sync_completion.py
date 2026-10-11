"""Native mail completion counts persisted ready threads and retries errored versions."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.core.config import settings
from src.domains.rag_spaces import mail_sync, source_worker_runtime
from src.domains.rag_spaces.models import RAGDocument, RAGMailSource, RAGSpace
from src.domains.rag_spaces.source_worker_lease import SourceWorkerLease
from src.domains.rag_spaces.storage_paths import stored_file_path
from tests.unit.domains.rag_spaces.test_mail_sync import LABEL, _message, _thread

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["unchanged_ready", "retry_error", "embedding_failed"])
async def test_native_mail_completion_uses_actual_thread_document_states(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    for flag in ("application_tools_enabled", "rag_spaces_enabled", "rag_spaces_mail_sync_enabled"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    monkeypatch.setattr("src.domains.shared.consultation_sink._collector_factory", None)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    token = f"native-{uuid4()}"
    source = RAGMailSource(
        user_id=owner,
        space_id=space_id,
        label_id=LABEL,
        label_name="Label",
        worker_id=token,
        sync_status="syncing",
    )
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    if scenario != "embedding_failed":
        async_session.add(
            RAGDocument(
                user_id=owner,
                space_id=space_id,
                mail_source_id=source_id,
                mail_thread_id="t1",
                mail_last_message_at=datetime.fromtimestamp(2000, tz=UTC),
                filename="old.md",
                original_filename="old.md",
                content_type="text/markdown",
                file_size=3,
                status="ready" if scenario == "unchanged_ready" else "error",
            )
        )
        path = stored_file_path(owner, space_id, "old.md")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"old")
    await async_session.execute(
        text(
            "UPDATE rag_mail_sources SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    await async_session.commit()

    @asynccontextmanager
    async def database():
        yield async_session

    for module in (mail_sync, source_worker_runtime):
        monkeypatch.setattr(module, "get_db_context", database)
    client = AsyncMock()
    client.get_profile.return_value = {"historyId": "900"}
    client.list_threads.return_value = {"threads": [{"id": "t1"}]}
    client.get_thread.return_value = _thread(
        _message(
            message_id="m1",
            at_ms=2_000_000,
            sender="a",
            to="b",
            subject="Literal subject",
            body="Controlled body",
        )
    )
    monkeypatch.setattr(mail_sync, "gmail_client_or_none", AsyncMock(return_value=client))

    async def processing(queued, *, counter):
        for kwargs in queued:
            document = await async_session.get(RAGDocument, kwargs["document_id"])
            document.status = "error" if scenario == "embedding_failed" else "ready"
        await async_session.commit()
        return (0, len(queued)) if scenario == "embedding_failed" else (len(queued), 0)

    monkeypatch.setattr(mail_sync, "process_queued", processing)
    await source_worker_runtime.run_native_source_worker(
        SourceWorkerLease("mail", source_id, space_id, owner, token)
    )
    current = await async_session.scalar(
        select(RAGMailSource)
        .where(RAGMailSource.id == source_id)
        .execution_options(populate_existing=True)
    )
    assert current.sync_status == ("error" if scenario == "embedding_failed" else "completed")
    assert current.synced_thread_count == int(scenario != "embedding_failed")
    documents = list(
        (
            await async_session.scalars(select(RAGDocument).where(RAGDocument.space_id == space_id))
        ).all()
    )
    assert len(documents) == 1
    assert documents[0].status == ("error" if scenario == "embedding_failed" else "ready")
