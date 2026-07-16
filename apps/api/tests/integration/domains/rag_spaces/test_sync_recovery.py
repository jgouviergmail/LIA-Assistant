"""Drive-sync durable recovery on real PostgreSQL (audit F001, Phase 1 T6).

Covers the source-level durable-job primitives (heartbeat / reclaim-or-fail /
fetch-recoverable) and the reaper's source branch (stuck SYNCING → re-leased and
re-driven, or dead-lettered at max attempts). The Drive client is not exercised:
``sync_folder_background`` is mocked so the test stays hermetic.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces import reapers
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.models import RAGDriveSource, RAGDriveSyncStatus, RAGSpace
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _make_source(db: AsyncSession, *, sync_status: str) -> RAGDriveSource:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    space = RAGSpace(name="sync-test", user_id=user.id)
    db.add(space)
    await db.flush()
    source = RAGDriveSource(
        space_id=space.id,
        user_id=user.id,
        folder_id="folder-123",
        folder_name="My Folder",
        sync_status=sync_status,
    )
    db.add(source)
    await db.commit()
    return source


async def _sync_row(db: AsyncSession, source_id: uuid.UUID) -> dict:
    res = await db.execute(
        text(
            "SELECT sync_status, attempts, lease_expires_at FROM rag_drive_sources "
            "WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    status, attempts, lease = res.one()
    return {"status": status, "attempts": attempts, "lease": lease}


async def test_reclaim_keeps_syncing_under_max(async_session: AsyncSession) -> None:
    src = await _make_source(async_session, sync_status=RAGDriveSyncStatus.SYNCING)
    await async_session.execute(
        text("UPDATE rag_drive_sources SET attempts = 1 WHERE id = :id"),
        {"id": str(src.id)},
    )
    await async_session.commit()
    status = await RAGJobsRepository(async_session).reclaim_or_fail_source(
        src.id, lease_ttl_s=300, max_attempts=3
    )
    assert status == RAGDriveSyncStatus.SYNCING
    row = await _sync_row(async_session, src.id)
    assert row["attempts"] == 2 and row["lease"] is not None


async def test_reclaim_dead_letters_at_max(async_session: AsyncSession) -> None:
    src = await _make_source(async_session, sync_status=RAGDriveSyncStatus.SYNCING)
    await async_session.execute(
        text("UPDATE rag_drive_sources SET attempts = :m WHERE id = :id"),
        {"m": settings.rag_job_max_attempts, "id": str(src.id)},
    )
    await async_session.commit()
    status = await RAGJobsRepository(async_session).reclaim_or_fail_source(
        src.id, lease_ttl_s=300, max_attempts=settings.rag_job_max_attempts
    )
    assert status == RAGDriveSyncStatus.ERROR


async def test_fetch_recoverable_sources(async_session: AsyncSession) -> None:
    repo = RAGJobsRepository(async_session)
    stuck = await _make_source(async_session, sync_status=RAGDriveSyncStatus.SYNCING)
    await async_session.execute(
        text(
            "UPDATE rag_drive_sources SET lease_expires_at = now() - interval '1 hour' "
            "WHERE id = :id"
        ),
        {"id": str(stuck.id)},
    )
    live = await _make_source(async_session, sync_status=RAGDriveSyncStatus.SYNCING)
    await async_session.execute(
        text(
            "UPDATE rag_drive_sources SET lease_expires_at = now() + interval '1 hour' "
            "WHERE id = :id"
        ),
        {"id": str(live.id)},
    )
    idle = await _make_source(async_session, sync_status=RAGDriveSyncStatus.IDLE)
    await async_session.commit()

    recoverable = set(await repo.fetch_recoverable_sources(limit=100))
    assert stuck.id in recoverable
    assert live.id not in recoverable  # lease still valid
    assert idle.id not in recoverable  # not syncing


async def test_heartbeat_source_only_when_syncing(async_session: AsyncSession) -> None:
    repo = RAGJobsRepository(async_session)
    src = await _make_source(async_session, sync_status=RAGDriveSyncStatus.SYNCING)
    assert await repo.heartbeat_source(src.id, 300) is True
    idle = await _make_source(async_session, sync_status=RAGDriveSyncStatus.IDLE)
    assert await repo.heartbeat_source(idle.id, 300) is False


async def test_reaper_recovers_stuck_source(monkeypatch, async_session: AsyncSession) -> None:
    @asynccontextmanager
    async def _fake_ctx():
        yield async_session

    monkeypatch.setattr(reapers, "get_db_context", _fake_ctx)
    # Mock the actual Drive sync (needs a Drive client) — assert it is re-driven.
    fake_sync = AsyncMock()
    monkeypatch.setattr("src.domains.rag_spaces.drive_sync.sync_folder_background", fake_sync)

    src = await _make_source(async_session, sync_status=RAGDriveSyncStatus.SYNCING)
    await async_session.execute(
        text(
            "UPDATE rag_drive_sources SET lease_expires_at = now() - interval '1 hour', "
            "attempts = 1 WHERE id = :id"
        ),
        {"id": str(src.id)},
    )
    await async_session.commit()

    await reapers.rag_job_reaper()

    fake_sync.assert_awaited_once()
    row = await _sync_row(async_session, src.id)
    assert row["status"] == RAGDriveSyncStatus.SYNCING  # re-leased, still recoverable
    assert row["attempts"] == 2


async def test_manual_acquire_resets_attempts_to_fresh(
    async_session: AsyncSession,
) -> None:
    """A user-initiated sync is a fresh run — try_acquire_sync_lock sets attempts=1,
    so manual re-syncs never consume the crash-recovery retry budget (F001)."""
    from src.domains.rag_spaces.drive_sync import RAGDriveSyncService

    src = await _make_source(async_session, sync_status=RAGDriveSyncStatus.IDLE)
    # Simulate attempts accumulated by earlier runs / recoveries.
    await async_session.execute(
        text("UPDATE rag_drive_sources SET attempts = 5 WHERE id = :id"),
        {"id": str(src.id)},
    )
    await async_session.commit()

    acquired = await RAGDriveSyncService(async_session).try_acquire_sync_lock(src.id)

    assert acquired is True
    row = await _sync_row(async_session, src.id)
    assert row["status"] == RAGDriveSyncStatus.SYNCING
    assert row["attempts"] == 1  # fresh run, not 6 — retry budget not consumed
