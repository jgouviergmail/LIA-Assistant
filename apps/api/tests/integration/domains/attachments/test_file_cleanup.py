"""File removal retains its record until the exact owned disk effect succeeds."""

import asyncio
import threading
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from src.core.config import settings
from src.domains.attachments.file_cleanup import cleanup_files
from src.domains.attachments.file_repository import AttachmentFileRepository
from src.domains.attachments.models import Attachment, AttachmentOrigin, AttachmentStatus
from src.domains.attachments.service import AttachmentService
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def test_expiration_and_removal_are_bounded_and_progress_on_the_next_sweep(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "attachments_cleanup_batch_size", 2)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        ids = [await _expired_file(db, owner, f"{owner}/{uuid4()}.png") for _ in range(3)]
        assert await AttachmentService(db).cleanup_expired() == {"deleted": 2, "errors": 0}
        assert len(list(await db.scalars(select(Attachment.id).where(Attachment.id.in_(ids))))) == 1
        assert await AttachmentService(db).cleanup_expired() == {"deleted": 1, "errors": 0}
        assert await db.scalar(select(Attachment.id).where(Attachment.id.in_(ids))) is None


async def _expired_file(db: AsyncSession, owner: UUID, path: str) -> UUID:
    row = Attachment(
        user_id=owner,
        original_filename="Fixture.png",
        stored_filename=Path(path).name,
        mime_type="image/png",
        file_size=4,
        file_path=path,
        content_type="image",
        origin=AttachmentOrigin.UPLOAD.value,
        status=AttachmentStatus.READY,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db.add(row)
    await db.commit()
    return row.id


async def test_failed_unlink_keeps_a_retryable_row_and_next_sweep_finishes(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    relative = f"{owner}/{uuid4()}.png"
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_bytes(b"data")

    def refuse_unlink(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("Injected disk refusal")

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        file_id = await _expired_file(db, owner, relative)
        with monkeypatch.context() as patcher:
            patcher.setattr(Path, "unlink", refuse_unlink)
            stats = await AttachmentService(db).cleanup_expired()
        row = await db.get(Attachment, file_id, populate_existing=True)
        assert row is not None, "The only durable path vanished before its file was removed"
        assert row.status == AttachmentStatus.DELETING
        assert row.io_owner_token is None
        assert stats == {"deleted": 0, "errors": 1}
        assert path.read_bytes() == b"data"
        stats = await AttachmentService(db).cleanup_expired()
        assert stats == {"deleted": 1, "errors": 0}
        assert await db.scalar(select(Attachment.id).where(Attachment.id == file_id)) is None
        assert not path.exists()


@pytest.mark.parametrize("attack", ["cross_owner", "escape"])
async def test_corrupt_relative_path_cannot_erase_another_directory(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    root = tmp_path / "attachments"
    root.mkdir()
    monkeypatch.setattr(settings, "attachments_storage_path", str(root))
    relative = f"{uuid4()}/protected.png" if attack == "cross_owner" else "../protected.png"
    victim = root / relative
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_bytes(b"keep")
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        file_id = await _expired_file(db, owner, relative)
        stats = await AttachmentService(db).cleanup_expired()
        assert victim.read_bytes() == b"keep"
        assert stats == {"deleted": 0, "errors": 1}
        row = await db.get(Attachment, file_id, populate_existing=True)
        assert row is not None and row.status == AttachmentStatus.DELETING


async def test_stale_removal_claim_cannot_settle_or_release_its_successor(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as first:
        file_id = await _expired_file(first, owner, f"{owner}/{uuid4()}.png")
        repo = AttachmentFileRepository(first)
        assert await repo.retire_expired(datetime.now(UTC)) == 1
        await first.commit()
        old = await repo.claim_removal(
            before=datetime.now(UTC), excluded=set(), attachment_id=file_id
        )
        assert old is not None
        await first.commit()
        async with AsyncSession(async_engine) as second:
            successor_repo = AttachmentFileRepository(second)
            # Inject a lapsed unlink lease; never a lapsed UPLOADED writer.
            await second.execute(
                update(Attachment)
                .where(Attachment.id == file_id)
                .values(io_claimed_at=datetime.now(UTC) - timedelta(hours=1))
            )
            await second.commit()
            successor = await successor_repo.claim_removal(
                before=datetime.now(UTC), excluded=set(), attachment_id=file_id
            )
            assert successor is not None and successor.owner_token != old.owner_token
            assert successor.fence > old.fence
            await second.commit()
            assert not await repo.finish_removal(old, removed=False)
            assert not await repo.finish_removal(old, removed=True)
            await first.commit()
            assert (
                await second.scalar(
                    select(Attachment.io_owner_token).where(Attachment.id == file_id)
                )
                == successor.owner_token
            )
            assert await successor_repo.finish_removal(successor, removed=True)
            await second.commit()


async def test_crash_after_unlink_replays_the_absent_path_without_losing_evidence(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    relative = f"{owner}/{uuid4()}.png"
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_bytes(b"data")
    commits = 0

    def fail_settle(session: Session) -> None:
        nonlocal commits
        commits += 1
        if commits == 2:
            raise OSError("Injected settle failure")

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        file_id = await _expired_file(db, owner, relative)
        await AttachmentFileRepository(db).retire_expired(datetime.now(UTC))
        await db.commit()
        event.listen(db.sync_session, "before_commit", fail_settle)
        try:
            with pytest.raises(OSError, match="settle failure"):
                await cleanup_files(db, ids=[file_id])
        finally:
            event.remove(db.sync_session, "before_commit", fail_settle)
            await db.rollback()
        assert not path.exists()
        row = await db.get(Attachment, file_id, populate_existing=True)
        assert row is not None and row.status == AttachmentStatus.DELETING
        assert row.io_owner_token is not None
        await db.execute(
            update(Attachment)
            .where(Attachment.id == file_id)
            .values(io_claimed_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()
        assert await cleanup_files(db, ids=[file_id]) == {"deleted": 1, "errors": 0}
        assert await db.scalar(select(Attachment.id).where(Attachment.id == file_id)) is None


async def test_cancelled_cleanup_joins_its_actual_unlink_before_releasing_ownership(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    relative = f"{owner}/{uuid4()}.png"
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_bytes(b"data")
    entered, release = asyncio.Event(), threading.Event()
    loop, original = asyncio.get_running_loop(), Path.unlink

    def held_unlink(self: Path, missing_ok: bool = False) -> None:
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(timeout=10):
            raise TimeoutError("Fixture did not release its unlink")
        original(self, missing_ok=missing_ok)

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        file_id = await _expired_file(db, owner, relative)
        await AttachmentFileRepository(db).retire_expired(datetime.now(UTC))
        await db.commit()
        with monkeypatch.context() as patcher:
            patcher.setattr(Path, "unlink", held_unlink)
            task = asyncio.create_task(cleanup_files(db, ids=[file_id]))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done() and path.exists()
                assert not db.in_transaction()
                async with AsyncSession(async_engine) as observer:
                    row = await observer.get(Attachment, file_id)
                    assert row is not None and row.io_owner_token is not None
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
                # The fixture too joins its disk task through an assertion failure.
                with suppress(asyncio.CancelledError):
                    await task
        assert not path.exists()
        assert await db.scalar(select(Attachment.id).where(Attachment.id == file_id)) is None
