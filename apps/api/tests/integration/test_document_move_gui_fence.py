"""GUI moves of other documents cannot cross a native account/target fence at commit."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.document_move import (
    execute_document_move,
    prepare_document_move,
)
from src.domains.agents.application.document_move_schemas import DocumentMoveInput
from src.domains.rag_spaces import document_ops
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.rag_spaces.schemas import RAGDocumentMoveRequest
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


async def test_gui_move_of_target_neighbor_waits_for_native_commit(
    async_engine, monkeypatch, tmp_path
):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    monkeypatch.setattr(
        document_ops, "get_reindex_status", AsyncMock(return_value={"in_progress": False})
    )
    monkeypatch.setattr(
        "src.domains.agents.application.document_move_scope.get_reindex_status",
        AsyncMock(return_value={"in_progress": False}),
    )
    owner = uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        seed.add(User(id=owner, email=f"move-fence-{owner}@example.test", is_active=True))
        await seed.flush()
        spaces = [RAGSpace(user_id=owner, name=f"Space {index}") for index in range(3)]
        seed.add_all(spaces)
        await seed.flush()
        documents = [
            RAGDocument(
                user_id=owner,
                space_id=spaces[index].id,
                filename=f"{index}.txt",
                original_filename=f"File {index}",
                file_size=4,
                content_type="text/plain",
                status="ready",
            )
            for index in range(2)
        ]
        seed.add_all(documents)
        await seed.commit()
        source, target, other = [space.id for space in spaces]
        selected, neighbor = [document.id for document in documents]
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            # Positive control: the same GUI writer succeeds without a held
            # native fence, in both directions, then is genuinely blocked.
            async with AsyncSession(async_engine, expire_on_commit=False) as writer:
                first = await document_ops.move_documents(
                    RAGSpaceService(writer),
                    target,
                    owner,
                    RAGDocumentMoveRequest(ids=[neighbor], target_space_id=other),
                )
                second = await document_ops.move_documents(
                    RAGSpaceService(writer),
                    other,
                    owner,
                    RAGDocumentMoveRequest(ids=[neighbor], target_space_id=target),
                )
                assert first.done == second.done == [neighbor]
            draft = await prepare_document_move(
                db,
                owner,
                DocumentMoveInput(space_id=source, document_ids=[selected], target_space_id=target),
            )
            original_commit = db.commit
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def commit():
                async with AsyncSession(async_engine, expire_on_commit=False) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as blocked:
                        await document_ops.move_documents(
                            RAGSpaceService(writer),
                            target,
                            owner,
                            RAGDocumentMoveRequest(ids=[neighbor], target_space_id=other),
                        )
                    assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                await original_commit()

            monkeypatch.setattr(db, "commit", commit)
            receipt = PreferenceWriteReceipt()
            await execute_document_move(db, owner, draft, receipt)
            assert receipt.committed
            assert (
                await db.scalar(select(RAGDocument.space_id).where(RAGDocument.id == neighbor))
                == target
            )
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
