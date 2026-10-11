"""Native movement keeps source rights, capacity, job gates and collision refusals."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_move import prepare_document_move
from src.domains.agents.application.document_move_schemas import DocumentMoveInput
from src.domains.rag_spaces.models import RAGDocument, RAGSpace

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "obstacle",
    [
        "system",
        "foreign",
        "drive",
        "mail",
        "meeting",
        "bookmark",
        "pending",
        "reindex",
        "pinned",
        "full",
        "collision",
    ],
)
async def test_source_move_guard_is_checked_before_draft_or_file_change(
    async_session, test_user, monkeypatch, tmp_path, obstacle
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    monkeypatch.setattr(
        "src.domains.agents.application.document_move_scope.get_reindex_status",
        AsyncMock(return_value={"in_progress": obstacle == "reindex"}),
    )
    owner = test_user.id
    source, target = RAGSpace(user_id=owner, name="Source"), RAGSpace(
        user_id=owner,
        name="Target",
        is_system=obstacle == "system",
        serving_embedding_model="controlled-pin" if obstacle == "pinned" else None,
    )
    async_session.add_all([source, target])
    await async_session.flush()
    doc = RAGDocument(
        user_id=owner,
        space_id=source.id,
        filename="selected.txt",
        original_filename="Selected",
        file_size=4,
        content_type="text/plain",
        status="pending" if obstacle == "pending" else "ready",
        source_type=obstacle if obstacle in {"drive", "mail", "meeting", "bookmark"} else "upload",
    )
    async_session.add(doc)
    if obstacle == "full":
        monkeypatch.setattr(settings, "rag_spaces_max_docs_per_space", 1)
        async_session.add(
            RAGDocument(
                user_id=owner,
                space_id=target.id,
                filename="neighbor.txt",
                original_filename="Neighbor",
                file_size=4,
                content_type="text/plain",
                status="ready",
            )
        )
    await async_session.commit()
    source_id, target_id, identity = source.id, target.id, doc.id
    original = tmp_path / str(owner) / str(source_id) / "selected.txt"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    destination = tmp_path / str(owner) / str(target_id) / "selected.txt"
    if obstacle == "collision":
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"kept")
    request = DocumentMoveInput(
        space_id=source_id,
        document_ids=[identity],
        target_space_id=uuid4() if obstacle == "foreign" else target_id,
    )
    with pytest.raises((BaseAPIException, CommandRejected)):
        await prepare_document_move(async_session, owner, request)
    assert original.read_bytes() == b"data"
    assert doc.space_id == source_id
    if obstacle == "collision":
        assert destination.read_bytes() == b"kept"
    else:
        assert not destination.exists()
