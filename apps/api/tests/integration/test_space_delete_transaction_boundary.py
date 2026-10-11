"""Actual independent indexing claims and GUI uploads cannot cross approved deletion locks."""

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.space_delete import (
    execute_space_deletion,
    prepare_space_deletion,
)
from src.domains.agents.application.space_delete_schemas import SpaceDeleteInput
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("writer_kind", ["job_claim", "gui_upload"])
@pytest.mark.parametrize("target", ["space", "document"])
async def test_independent_document_writers_wait_for_deletion(
    async_engine, monkeypatch, tmp_path, writer_kind, target
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, identity, document = uuid4(), uuid4(), uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(User(id=owner, email=f"space-delete-fence-{owner}@example.test", is_active=True))
        await seed.flush()
        seed.add(RAGSpace(id=identity, user_id=owner, name="Personal deletion"))
        await seed.flush()
        seed.add(
            RAGDocument(
                id=document,
                space_id=identity,
                user_id=owner,
                filename="file.txt",
                original_filename="File",
                file_size=1,
                content_type="text/plain",
                status="pending",
            )
        )
        await seed.commit()
    method = "delete_space" if target == "space" else "delete_selected_document_rows"
    source_delete = getattr(RAGSpaceService, method)
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def probe(service, *args, **kwargs):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as waiting:
                        if writer_kind == "job_claim":
                            await RAGJobsRepository(writer).claim_document(
                                document, "controlled-worker", 30
                            )
                        else:
                            # The account/parent fence must precede even reading
                            # the submitted file or writing any bytes to disk.
                            await RAGSpaceService(writer).upload_document(
                                identity,
                                owner,
                                UploadFile(filename="new.txt", file=BytesIO(b"new contents")),
                            )
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_delete(service, *args, **kwargs)

            monkeypatch.setattr(RAGSpaceService, method, probe)
            prepare, execute = prepare_space_deletion, execute_space_deletion
            selected = SpaceDeleteInput(space_id=identity)
            if target == "document":
                from src.domains.agents.application.document_delete import (
                    execute_document_deletion,
                    prepare_document_deletion,
                )
                from src.domains.agents.application.document_delete_schemas import (
                    DocumentDeleteInput,
                )

                prepare, execute = prepare_document_deletion, execute_document_deletion
                selected = DocumentDeleteInput(space_id=identity, document_ids=[document])
            draft = await prepare(db, owner, selected)
            receipt = PreferenceWriteReceipt()
            await execute(db, owner, draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
