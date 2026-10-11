"""The native reader sees exactly the composer's owned ready-document catalogue."""

from uuid import uuid4

import pytest
from sqlalchemy import update

from src.core.config import settings
from src.domains.agents.application.space_read import read_space_ui
from src.domains.agents.application.space_read_schemas import SpaceUIQuery
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_account_document_catalogue_keeps_inactive_spaces_exact_counts_and_literal_filter(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    owner, foreign = test_user.id, uuid4()
    async_session.add(User(id=foreign, email=f"catalogue-{foreign}@example.test", is_active=True))
    await async_session.flush()
    personal = RAGSpace(user_id=owner, name="Paused personal", is_active=False)
    other = RAGSpace(user_id=foreign, name="Foreign")
    system = RAGSpace(user_id=None, name="System", is_system=True)
    corrupt_system = RAGSpace(user_id=owner, name="System owner inconsistency", is_system=True)
    async_session.add_all([personal, other, system, corrupt_system])
    await async_session.flush()
    for space, actor, filename, status in [
        (personal, owner, "100% literal.txt", "ready"),
        (personal, owner, "Second ready.txt", "ready"),
        (personal, owner, "Not indexed.txt", "pending"),
        (other, foreign, "Foreign private.txt", "ready"),
        (system, None, "System private.txt", "ready"),
        (corrupt_system, owner, "System owned private.txt", "ready"),
    ]:
        async_session.add(
            RAGDocument(
                space_id=space.id,
                user_id=actor,
                filename="private-storage.txt",
                original_filename=filename,
                file_size=17,
                content_type="text/plain",
                status=status,
            )
        )
    await async_session.commit()
    result = await read_space_ui(
        async_session, owner, SpaceUIQuery(section="attachable_documents", limit=1)
    )
    assert result.total == 2 and result.next_offset == 1 and len(result.attachable_documents) == 1
    assert (
        result.attachable_documents[0].space_name == "Paused personal"
        and not result.attachable_documents[0].space_is_active
    )
    selected = await read_space_ui(
        async_session, owner, SpaceUIQuery(section="attachable_documents", q="100%", limit=10)
    )
    assert (
        selected.total == 1
        and selected.attachable_documents[0].original_filename == "100% literal.txt"
    )
    assert (
        "private-storage" not in selected.model_dump_json()
        and "private.txt" not in selected.model_dump_json()
    )


async def test_catalogue_reobserves_parent_metadata_from_sql_not_identity_map(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Old name", is_active=True)
    async_session.add(space)
    await async_session.flush()
    async_session.add(
        RAGDocument(
            space_id=space.id,
            user_id=owner,
            filename="private.txt",
            original_filename="Public name",
            file_size=1,
            content_type="text/plain",
            status="ready",
        )
    )
    await async_session.commit()
    query = SpaceUIQuery(section="attachable_documents")
    await read_space_ui(async_session, owner, query)
    await async_session.execute(
        update(RAGSpace)
        .where(RAGSpace.id == space.id)
        .values(name="Current name", is_active=False)
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    result = await read_space_ui(async_session, owner, query)
    assert (
        result.attachable_documents[0].space_name == "Current name"
        and not result.attachable_documents[0].space_is_active
    )
