"""Actual independent indexing claims and GUI uploads cannot cross approved deletion locks."""

from collections.abc import AsyncIterator, Awaitable, Callable
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.domains.agents.application.document_delete import (
    execute_document_deletion,
    prepare_document_deletion,
)
from src.domains.agents.application.document_delete_schemas import DocumentDeleteInput
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
from src.infrastructure.database.server_bounds import engine_server_settings
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def bounded_writer_engine(
    test_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncEngine]:
    """Apply the real server bound to the upload session and its independent claim."""
    monkeypatch.setattr(settings, "database_lock_timeout_ms", 100)
    engine = create_async_engine(
        test_database_url,
        poolclass=NullPool,
        connect_args={"server_settings": engine_server_settings(), "timeout": 30},
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.parametrize("writer_kind", ["job_claim", "gui_upload"])
@pytest.mark.parametrize("target", ["space", "document"])
async def test_independent_document_writers_wait_for_deletion(
    async_engine: AsyncEngine,
    bounded_writer_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    writer_kind: str,
    target: str,
) -> None:
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
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def assert_writer_is_blocked() -> None:
                async with AsyncSession(bounded_writer_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    with pytest.raises(DBAPIError) as waiting:
                        if writer_kind == "job_claim":
                            await RAGJobsRepository(writer).claim_document(
                                document, "controlled-worker", 30
                            )
                        else:
                            # The account/parent fence must precede even reading
                            # the submitted file or writing any bytes to disk.
                            with BytesIO(b"new contents") as source:
                                file = UploadFile(filename="new.txt", file=source)
                                try:
                                    await RAGSpaceService(writer).upload_document(
                                        identity, owner, file
                                    )
                                finally:
                                    assert source.tell() == 0
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"

            def observe[**P, T](
                delete_rows: Callable[P, Awaitable[T]],
            ) -> Callable[P, Awaitable[T]]:
                async def probe(*args: P.args, **kwargs: P.kwargs) -> T:
                    await assert_writer_is_blocked()
                    return await delete_rows(*args, **kwargs)

                return probe

            receipt = PreferenceWriteReceipt()
            if target == "document":
                monkeypatch.setattr(
                    RAGSpaceService,
                    "delete_selected_document_rows",
                    observe(RAGSpaceService.delete_selected_document_rows),
                )
                draft = await prepare_document_deletion(
                    db, owner, DocumentDeleteInput(space_id=identity, document_ids=[document])
                )
                await execute_document_deletion(db, owner, draft, receipt)
            else:
                monkeypatch.setattr(
                    RAGSpaceService, "delete_space", observe(RAGSpaceService.delete_space)
                )
                draft = await prepare_space_deletion(db, owner, SpaceDeleteInput(space_id=identity))
                await execute_space_deletion(db, owner, draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
