"""A source keeps its lease while its documents embed, on real PostgreSQL (audit F001).

The reaper recovers a source that is SYNCING under an expired lease, and the
document reaper leaves a syncing source's PENDING documents alone only while
that lease is alive. Both rest on one promise: a live sync renews its lease.
It did, before each thread or file it read — and not once while it embedded
what it had queued. Measured in production on 2026-11-09: 13 minutes of
embedding under a 5-minute lease, a second full sync started beside the first,
32 documents requeued under it.

The embedding itself is a double (it needs a provider); the lease, its renewal
and the reaper's two queries are the real ones.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces import source_lease_keepalive
from src.domains.rag_spaces.drive_ingest import process_queued
from src.domains.rag_spaces.jobs_repository import (
    DRIVE_SOURCE_TABLE,
    MAIL_SOURCE_TABLE,
    RAGJobsRepository,
)
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGDriveSyncStatus,
    RAGMailSource,
    RAGSourceSyncStatus,
    RAGSpace,
)
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

#: Renewal cadence for the test, in seconds. The setting's real floor is far
#: above; only the ratio to the work's duration matters here.
_CADENCE = 0.05
#: Renewals the embedding double waits for before it returns: the lease the
#: source starts with is already expired, so one renewal is what saves it and
#: the second proves the cadence goes on.
_RENEWALS_AWAITED = 2
_PATIENCE = 10.0


async def _make_source(db: AsyncSession, table: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A SYNCING source whose lease has just run out, as after its last read."""
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    space = RAGSpace(name="lease-test", user_id=user.id)
    db.add(space)
    await db.flush()
    source: RAGMailSource | RAGDriveSource
    if table == MAIL_SOURCE_TABLE:
        source = RAGMailSource(
            space_id=space.id,
            user_id=user.id,
            label_id="Label_7",
            label_name="Kept",
            sync_status=RAGSourceSyncStatus.SYNCING,
        )
    else:
        source = RAGDriveSource(
            space_id=space.id,
            user_id=user.id,
            folder_id="folder-7",
            folder_name="Kept",
            sync_status=RAGDriveSyncStatus.SYNCING,
        )
    db.add(source)
    await db.flush()
    await db.execute(
        text(
            f"UPDATE {table} SET lease_expires_at = now() - interval '1 second', "
            "heartbeat_at = now() - interval '10 minutes', attempts = 1 WHERE id = :id"
        ),
        {"id": str(source.id)},
    )
    await db.commit()
    return source.id, space.id, user.id


async def _pending_document(
    db: AsyncSession, table: str, source_id: uuid.UUID, space_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    """A document its sync queued and has not embedded yet, older than the grace."""
    mail = table == MAIL_SOURCE_TABLE
    document = RAGDocument(
        space_id=space_id,
        user_id=user_id,
        filename="queued.md",
        original_filename="queued.md",
        file_size=10,
        content_type="text/markdown",
        status=RAGDocumentStatus.PENDING,
        source_type=RAGDocumentSourceType.MAIL if mail else RAGDocumentSourceType.DRIVE,
        mail_source_id=source_id if mail else None,
        mail_thread_id="t1" if mail else None,
        drive_source_id=None if mail else source_id,
        drive_file_id=None if mail else "f1",
    )
    db.add(document)
    await db.flush()
    await db.execute(
        text("UPDATE rag_documents SET created_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": str(document.id)},
    )
    await db.commit()
    return document.id


class _Embedding:
    """The embedding phase: it lasts until the lease has been renewed twice."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, db: AsyncSession) -> None:
        self.renewed = 0
        self._enough = asyncio.Event()
        real = RAGJobsRepository.heartbeat_source

        async def counting(repo: RAGJobsRepository, *args: Any, **kwargs: Any) -> bool:
            renewed = await real(repo, *args, **kwargs)
            self.renewed += 1
            if self.renewed >= _RENEWALS_AWAITED:
                self._enough.set()
            return renewed

        @asynccontextmanager
        async def _session() -> AsyncIterator[AsyncSession]:
            yield db

        monkeypatch.setattr(RAGJobsRepository, "heartbeat_source", counting)
        monkeypatch.setattr(source_lease_keepalive, "get_db_context", _session)
        monkeypatch.setattr(
            source_lease_keepalive.settings, "rag_job_heartbeat_interval_seconds", _CADENCE
        )

    async def __call__(self, **_kwargs: Any) -> bool:
        await asyncio.wait_for(self._enough.wait(), _PATIENCE)
        return True


async def _lease_seconds_left(db: AsyncSession, table: str, source_id: uuid.UUID) -> float:
    result = await db.execute(
        text(f"SELECT extract(epoch FROM lease_expires_at - now()) FROM {table} " "WHERE id = :id"),
        {"id": str(source_id)},
    )
    return float(result.scalar_one())


@pytest.mark.parametrize("table", [MAIL_SOURCE_TABLE, DRIVE_SOURCE_TABLE])
async def test_the_lease_is_alive_again_once_the_documents_have_embedded(
    monkeypatch: pytest.MonkeyPatch, async_session: AsyncSession, table: str
) -> None:
    source_id, _space, _user = await _make_source(async_session, table)
    embedding = _Embedding(monkeypatch, async_session)
    assert await _lease_seconds_left(async_session, table, source_id) < 0

    synced, failed = await process_queued(
        [{"document_id": uuid.uuid4()}],
        source_id=source_id,
        source_table=table,
        counter=MagicMock(),
        processor=embedding,
    )

    assert (synced, failed) == (1, 0)
    assert embedding.renewed >= _RENEWALS_AWAITED
    # Renewed for a whole lease, from the database's own clock.
    left = await _lease_seconds_left(async_session, table, source_id)
    assert left > settings.rag_job_lease_ttl_seconds - _PATIENCE


@pytest.mark.parametrize("table", [MAIL_SOURCE_TABLE, DRIVE_SOURCE_TABLE])
async def test_the_reaper_leaves_the_source_and_its_queued_documents_alone(
    monkeypatch: pytest.MonkeyPatch, async_session: AsyncSession, table: str
) -> None:
    source_id, space_id, user_id = await _make_source(async_session, table)
    document_id = await _pending_document(async_session, table, source_id, space_id, user_id)
    jobs = RAGJobsRepository(async_session)
    # Before the embedding starts, both are what the reaper would take: the
    # lease ran out, and the document is PENDING past the grace window.
    assert source_id in await jobs.fetch_recoverable_sources(limit=100, table=table)
    grace = settings.rag_job_reaper_grace_seconds
    assert document_id in await jobs.fetch_recoverable_documents(grace_s=grace, limit=100)
    await async_session.commit()

    await process_queued(
        [{"document_id": document_id}],
        source_id=source_id,
        source_table=table,
        counter=MagicMock(),
        processor=_Embedding(monkeypatch, async_session),
    )

    assert source_id not in await jobs.fetch_recoverable_sources(limit=100, table=table)
    assert document_id not in await jobs.fetch_recoverable_documents(grace_s=grace, limit=100)
