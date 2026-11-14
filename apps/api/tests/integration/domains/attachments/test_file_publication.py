"""File effects have durable ownership before disk writes and joined cancellation."""

import asyncio
import io
import threading
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import event, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.conversation_execution import ExecutionRevoked
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.exceptions import BaseAPIException
from src.domains.attachments.file_contracts import FileWriteResult, UploadMetadata
from src.domains.attachments.file_publication import publish_file
from src.domains.attachments.file_repository import AttachmentFileRepository
from src.domains.attachments.models import Attachment, AttachmentStatus
from src.domains.attachments.service import AttachmentService
from src.domains.conversations.models import Conversation
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration
_PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic fixture bytes"
_METADATA = UploadMetadata("Fixture.png", "image/png", "image", ".png")


def _write(path: Path) -> FileWriteResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_PNG)
    return FileWriteResult(len(_PNG))


async def test_a_refused_commit_cannot_leave_an_untracked_file(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real transaction fails before commit; no unowned disk effect may escape it."""
    owner_id = await commit_owner(async_engine, committed_user_ids)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))

    def refuse_commit(session: Session) -> None:
        raise OSError("Injected database commit failure")

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        event.listen(db.sync_session, "before_commit", refuse_commit)
        uploaded = UploadFile(file=io.BytesIO(_PNG), filename="Fixture.png")
        try:
            with pytest.raises(BaseAPIException):
                await AttachmentService(db).upload(owner_id, uploaded)
        finally:
            event.remove(db.sync_session, "before_commit", refuse_commit)
            await db.rollback()
            await uploaded.close()

    async with AsyncSession(async_engine) as observer:
        assert (
            await observer.scalar(select(Attachment.id).where(Attachment.user_id == owner_id))
            is None
        )
    assert list(tmp_path.rglob("*.png")) == [], "File exists without any durable cleanup record"


async def test_failed_publication_retains_the_already_written_file_for_cleanup(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second commit fails AFTER disk effects; the durable path is never lost."""
    owner_id = await commit_owner(async_engine, committed_user_ids)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    commits = 0

    def refuse_publication(session: Session) -> None:
        nonlocal commits
        commits += 1
        if commits == 2:
            raise OSError("Injected publication failure")

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        event.listen(db.sync_session, "before_commit", refuse_publication)
        try:
            with pytest.raises(OSError, match="publication failure"):
                await publish_file(
                    db, owner_id=owner_id, metadata=_METADATA, target=None, write=_write
                )
        finally:
            event.remove(db.sync_session, "before_commit", refuse_publication)

    async with AsyncSession(async_engine) as observer:
        row = await observer.scalar(select(Attachment).where(Attachment.user_id == owner_id))
        assert row is not None and row.status == AttachmentStatus.DELETING
        assert row.io_owner_token is None and row.io_worker_id is None
        assert (tmp_path / row.file_path).read_bytes() == _PNG
        assert row.deletion_reason == "upload_failed"


@pytest.mark.parametrize("interrupt", ["cancel", "rotate"])
async def test_a_paused_disk_writer_is_owned_joined_and_cannot_publish_after_reset(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt: str,
) -> None:
    """Observe committed ownership and no idle transaction DURING the actual thread."""
    owner_id = await commit_owner(async_engine, committed_user_ids)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    target = ConversationRef(owner_id, uuid4(), ConversationKind.SECONDARY, 1, uuid4())
    async with AsyncSession(async_engine) as setup:
        setup.add(
            Conversation(
                id=target.id,
                user_id=owner_id,
                kind=target.kind,
                revision=target.revision,
                runtime_id=target.runtime_id,
                title="Publication fixture",
            )
        )
        await setup.commit()

    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()

    def held_write(path: Path) -> FileWriteResult:
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(timeout=10):
            raise TimeoutError("Fixture did not release its writer")
        return _write(path)

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        writer_pid = await db.scalar(text("SELECT pg_backend_pid()"))
        task = asyncio.create_task(
            publish_file(db, owner_id=owner_id, metadata=_METADATA, target=target, write=held_write)
        )
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            assert not db.in_transaction()
            async with AsyncSession(async_engine) as observer:
                row = await observer.scalar(
                    select(Attachment).where(Attachment.user_id == owner_id)
                )
                assert row is not None and row.status == AttachmentStatus.UPLOADED
                assert row.io_owner_token is not None and row.io_worker_id is not None
                assert not (tmp_path / row.file_path).exists()
                assert (
                    await observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE pid=:pid "
                            "AND state='idle in transaction'"
                        ),
                        {"pid": writer_pid},
                    )
                    == 0
                )
                await observer.rollback()
                if interrupt == "rotate":
                    await observer.execute(
                        update(Conversation)
                        .where(Conversation.id == target.id)
                        .values(revision=2, runtime_id=uuid4())
                    )
                    await observer.commit()
            if interrupt == "cancel":
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done(), "Cancelling the await did not stop the disk writer"
            release.set()
            with pytest.raises(
                asyncio.CancelledError if interrupt == "cancel" else ExecutionRevoked
            ):
                await task
        finally:
            release.set()
            # A failing assertion still owns and joins the paused writer.
            with suppress(asyncio.CancelledError, ExecutionRevoked):
                await task
    async with AsyncSession(async_engine) as observer:
        row = await observer.scalar(select(Attachment).where(Attachment.user_id == owner_id))
        assert row is not None and row.status == AttachmentStatus.DELETING
        assert row.io_owner_token is None
        assert (tmp_path / row.file_path).read_bytes() == _PNG


async def test_upload_crash_is_never_inferred_from_elapsed_time(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    """An unknown worker may still write; neither expiry nor a removal lease retires it."""
    owner_id = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        repo = AttachmentFileRepository(db)
        ticket = await repo.stage_upload(owner_id, _METADATA, None)
        await db.commit()
        past = datetime.now(UTC) - timedelta(days=3)
        await db.execute(
            update(Attachment)
            .where(Attachment.id == ticket.attachment_id)
            .values(expires_at=past, io_claimed_at=past)
        )
        await db.commit()
        assert await repo.retire_expired(datetime.now(UTC)) == 0
        assert await repo.claim_removal(before=datetime.now(UTC), excluded=set()) is None
        await db.commit()
        row = await db.get(Attachment, ticket.attachment_id)
        assert row is not None and row.status == AttachmentStatus.UPLOADED
        assert row.io_owner_token == ticket.owner_token


async def test_stopped_boot_recovery_is_exact_idempotent_and_never_republishes(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    old_worker, live_worker = uuid4(), uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        repo = AttachmentFileRepository(db)
        monkeypatch.setattr("src.domains.attachments.file_repository.WORKER_BOOT_ID", old_worker)
        stopped = await repo.stage_upload(owner, _METADATA, None)
        await db.commit()
        monkeypatch.setattr("src.domains.attachments.file_repository.WORKER_BOOT_ID", live_worker)
        live = await repo.stage_upload(owner, _METADATA, None)
        await db.commit()
        assert await repo.retire_stopped_worker(old_worker) == 1
        await db.commit()
        assert await repo.retire_stopped_worker(old_worker) == 0
        with pytest.raises(ExecutionRevoked):
            await repo.publish_upload(stopped, FileWriteResult(1), None)
        await db.rollback()
        survivor = await db.get(Attachment, live.attachment_id)
        assert survivor is not None and survivor.status == AttachmentStatus.UPLOADED
        assert survivor.io_owner_token == live.owner_token
