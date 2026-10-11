"""Exact native consent removes a personal source space, cascades and files after commit."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.space_delete import (
    execute_space_deletion,
    prepare_space_deletion,
)
from src.domains.agents.application.space_delete_schemas import SpaceDeleteInput
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDriveSource,
    RAGMailSource,
    RAGSpace,
)
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


async def seed_space(db, owner):
    space = RAGSpace(user_id=owner, name="Personal corpus")
    db.add(space)
    await db.flush()
    doc = RAGDocument(
        space_id=space.id,
        user_id=owner,
        filename="server-file.txt",
        original_filename="Literal document.txt",
        file_size=12,
        content_type="text/plain",
        status="ready",
    )
    db.add_all(
        [
            doc,
            RAGDriveSource(
                space_id=space.id, user_id=owner, folder_id="folder-id", folder_name="Folder"
            ),
            RAGMailSource(
                space_id=space.id, user_id=owner, label_id="label-id", label_name="Label"
            ),
        ]
    )
    await db.commit()
    return space.id, doc.id


async def test_deletion_prepares_without_effect_then_removes_cascades_and_files(
    async_session, test_user, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    identity, document = await seed_space(async_session, owner)
    async_session.add(
        RAGChunk(
            document_id=document,
            space_id=identity,
            user_id=owner,
            chunk_index=0,
            content="Private source text",
            embedding=[0.0] * 1536,
            embedding_model="controlled-test-model",
        )
    )
    await async_session.commit()
    directory = tmp_path / str(owner) / str(identity)
    directory.mkdir(parents=True)
    (directory / "server-file.txt").write_text("Real contents", encoding="utf-8")
    draft = await prepare_space_deletion(async_session, owner, SpaceDeleteInput(space_id=identity))
    assert directory.exists() and await async_session.get(RAGSpace, identity)
    assert draft.before["space_delete"]["documents"] == 1
    assert draft.before["space_delete"]["chunks"] == 1
    assert "Private source text" not in str(draft.model_dump(mode="json"))
    receipt = PreferenceWriteReceipt()
    await execute_space_deletion(async_session, owner, draft, receipt)
    assert receipt.committed and not directory.exists()
    assert await async_session.get(RAGSpace, identity, populate_existing=True) is None
    assert await async_session.get(RAGDocument, document, populate_existing=True) is None
    for model in (RAGDriveSource, RAGMailSource, RAGChunk):
        assert (
            await async_session.scalar(
                select(func.count(model.id)).where(model.space_id == identity)
            )
            == 0
        )


@pytest.mark.parametrize("kind", ["meetings", "bookmarks"])
async def test_managed_spaces_keep_source_refusal(async_session, test_user, monkeypatch, kind):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = RAGSpace(user_id=test_user.id, name="Managed personal corpus", kind=kind)
    async_session.add(space)
    await async_session.commit()
    with pytest.raises(BaseAPIException) as refusal:
        await prepare_space_deletion(
            async_session, test_user.id, SpaceDeleteInput(space_id=space.id)
        )
    assert refusal.value.detail == {"code": "space_managed_by_domain", "kind": kind}


@pytest.mark.parametrize(
    "obstacle",
    [
        "new_document",
        "false_source",
        "lost_ack",
        "cancelled_ack",
        "cleanup_failed",
        "cleanup_cancelled",
    ],
)
async def test_deletion_conflicts_and_commit_uncertainty_do_not_delete_files_early(
    async_session, test_user, monkeypatch, tmp_path, obstacle
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    identity, _ = await seed_space(async_session, owner)
    directory = tmp_path / str(owner) / str(identity)
    directory.mkdir(parents=True)
    draft = await prepare_space_deletion(async_session, owner, SpaceDeleteInput(space_id=identity))
    await async_session.commit()
    if obstacle == "new_document":
        async_session.add(
            RAGDocument(
                space_id=identity,
                user_id=owner,
                filename="new.txt",
                original_filename="New document",
                file_size=3,
                content_type="text/plain",
                status="pending",
            )
        )
        await async_session.commit()
    elif obstacle == "false_source":
        monkeypatch.setattr(RAGSpaceService, "delete_space", AsyncMock())
    elif obstacle == "cleanup_failed":
        monkeypatch.setattr(
            "src.domains.rag_spaces.space_deletion.cleanup_space_files",
            AsyncMock(return_value=False),
        )
    elif obstacle == "cleanup_cancelled":
        monkeypatch.setattr(
            "src.domains.rag_spaces.space_deletion.cleanup_space_files",
            AsyncMock(side_effect=asyncio.CancelledError()),
        )
    else:
        original = async_session.commit

        async def lost_ack():
            await original()
            if obstacle == "cancelled_ack":
                raise asyncio.CancelledError()
            raise OSError("Controlled lost acknowledgement")

        monkeypatch.setattr(async_session, "commit", lost_ack)
    receipt = PreferenceWriteReceipt()
    if obstacle in {"cleanup_failed", "cleanup_cancelled"}:
        await execute_space_deletion(async_session, owner, draft, receipt)
        assert receipt.committed and receipt.values["space_delete"]["file_cleanup_pending"] is True
    else:
        with pytest.raises((ResourceConflictError, CommandRejected, ValueError)) as refusal:
            await execute_space_deletion(async_session, owner, draft, receipt)
        assert not receipt.committed
        if obstacle in {"lost_ack", "cancelled_ack"}:
            assert (
                isinstance(refusal.value, CommandRejected)
                and refusal.value.code == "COMPLETION_UNKNOWN"
            )
    await async_session.rollback()
    actual = await async_session.get(RAGSpace, identity, populate_existing=True)
    assert (actual is None) == (
        obstacle in {"lost_ack", "cancelled_ack", "cleanup_failed", "cleanup_cancelled"}
    )
    assert directory.exists()


@pytest.mark.parametrize("job", ["document", "drive", "mail", "managed"])
async def test_active_indexing_or_sync_is_finitely_refused_by_actual_tool(
    async_session, test_user, monkeypatch, job
):
    from contextlib import asynccontextmanager

    from langgraph.store.memory import InMemoryStore

    from src.domains.agents.tools import application_space_tools
    from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    owner = test_user.id
    identity, document = await seed_space(async_session, owner)
    if job == "managed":
        row = await async_session.get(RAGSpace, identity)
        row.kind = "meetings"
    elif job == "document":
        row = await async_session.get(RAGDocument, document)
        row.status = "processing"
    else:
        model = RAGDriveSource if job == "drive" else RAGMailSource
        row = await async_session.scalar(select(model).where(model.space_id == identity))
        row.sync_status = "syncing"
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_space_tools, "get_db_context", session)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_space_tools.delete_lia_knowledge_space_tool.coroutine(
            request={"space_id": identity},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert not result.success and result.error_code == (
        "CONSTRAINT_VIOLATION" if job == "managed" else "BUSY"
    ), result.model_dump()
    assert not result.registry_updates and await async_session.get(RAGSpace, identity)
