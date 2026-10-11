"""Real automatic indexing stops before spending and never publishes after account revocation."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.rag_spaces import processing
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDocumentStatus
from src.domains.users.models import User
from tests.integration.domains.bookmarks.test_bookmarks_db import _document, _space

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "inactive",
        "deleted",
        "keep_off",
        "rag_off",
        "revoked_during_batch",
        "taken_over",
        "quota",
    ],
)
async def test_bookmark_processing_checks_live_authority_before_spend_and_publication(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "bookmarks_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = await _space(async_session, test_user)
    doc = await _document(async_session, test_user, space, RAGDocumentStatus.PENDING)
    identity, space_id, filename = doc.id, space.id, doc.filename
    path = tmp_path / str(owner) / str(space_id) / filename
    path.parent.mkdir(parents=True)
    path.write_text("A saved answer that must require an active account.", encoding="utf-8")
    await async_session.commit()
    if scenario == "inactive":
        test_user.is_active = False
    elif scenario == "deleted":
        from datetime import UTC, datetime

        test_user.deleted_at = datetime.now(UTC)
    elif scenario == "keep_off":
        monkeypatch.setattr(settings, "bookmarks_enabled", False)
    elif scenario == "rag_off":
        monkeypatch.setattr(settings, "rag_spaces_enabled", False)
    await async_session.commit()

    @asynccontextmanager
    async def database():
        yield async_session

    monkeypatch.setattr(processing, "get_db_context", database)
    if scenario == "quota":
        from unittest.mock import AsyncMock

        monkeypatch.setattr(
            "src.domains.rag_spaces.bookmark_processing_guard.spend_blocked",
            AsyncMock(return_value=True),
        )
    calls = []

    class Embeddings:
        model_name = settings.rag_spaces_embedding_model.removeprefix("models/")

        async def aembed_documents(self, texts):
            assert not async_session.in_transaction()
            calls.append(texts)
            if scenario == "revoked_during_batch":
                account = await async_session.scalar(select(User).where(User.id == owner))
                account.is_active = False
                await async_session.commit()
            elif scenario == "taken_over":
                from sqlalchemy import update

                await async_session.execute(
                    update(RAGDocument)
                    .where(RAGDocument.id == identity)
                    .values(worker_id="new-bookmark-worker")
                )
                await async_session.commit()
            return [[0.001] * settings.rag_spaces_embedding_dimensions for _ in texts]

    monkeypatch.setattr(processing, "get_rag_embeddings", lambda: Embeddings())
    ok = await processing.process_document(
        document_id=identity,
        space_id=space_id,
        user_id=owner,
        filename=filename,
        original_filename="saved.md",
        content_type="text/markdown",
    )
    assert ok == (scenario == "valid")
    assert len(calls) == int(scenario in {"valid", "revoked_during_batch", "taken_over"})
    count = await async_session.scalar(
        select(func.count(RAGChunk.id)).where(RAGChunk.document_id == identity)
    )
    assert bool(count) == (scenario == "valid")
    status = await async_session.scalar(
        select(RAGDocument.status).where(RAGDocument.id == identity)
    )
    expected_status = RAGDocumentStatus.READY if scenario == "valid" else RAGDocumentStatus.ERROR
    if scenario == "taken_over":
        expected_status = RAGDocumentStatus.PROCESSING
    assert status == expected_status
    assert path.exists()
