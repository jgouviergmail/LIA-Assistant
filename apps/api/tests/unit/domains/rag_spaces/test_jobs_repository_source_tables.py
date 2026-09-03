"""The durable source jobs serve Drive folders AND Gmail labels (ADR-262).

The table is a parameter validated against an allowlist — the only way a
name reaches the SQL text — and a PENDING document of a live label sync is a
live job the reaper must leave alone, exactly like one of a live Drive sync.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.rag_spaces.jobs_repository import (
    DRIVE_SOURCE_TABLE,
    MAIL_SOURCE_TABLE,
    RAGJobsRepository,
    source_table,
)

pytestmark = pytest.mark.unit


def _repo() -> tuple[RAGJobsRepository, AsyncMock]:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1, first=lambda: ("syncing",)))
    return RAGJobsRepository(db), db


def _sql(db: AsyncMock) -> str:
    return str(db.execute.await_args.args[0].text)


def test_only_the_two_source_tables_are_accepted() -> None:
    assert source_table(DRIVE_SOURCE_TABLE) == "rag_drive_sources"
    assert source_table(MAIL_SOURCE_TABLE) == "rag_mail_sources"
    with pytest.raises(ValueError, match="not a synced-source table"):
        source_table("rag_documents; DROP TABLE users")


async def test_drive_stays_the_default_table() -> None:
    repo, db = _repo()
    await repo.heartbeat_source(uuid.uuid4(), 60)
    assert "UPDATE rag_drive_sources SET" in _sql(db)


async def test_mail_sources_use_the_same_three_jobs() -> None:
    repo, db = _repo()
    await repo.heartbeat_source(uuid.uuid4(), 60, table=MAIL_SOURCE_TABLE)
    assert "UPDATE rag_mail_sources SET" in _sql(db)
    await repo.reclaim_or_fail_source(uuid.uuid4(), 60, 3, table=MAIL_SOURCE_TABLE)
    assert "UPDATE rag_mail_sources SET" in _sql(db)
    db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: []))
    await repo.fetch_recoverable_sources(10, table=MAIL_SOURCE_TABLE)
    assert "SELECT id FROM rag_mail_sources WHERE" in _sql(db)


async def test_a_pending_document_of_a_live_label_sync_is_not_recoverable() -> None:
    repo, db = _repo()
    db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: []))
    await repo.fetch_recoverable_documents(grace_s=60, limit=10)
    sql = _sql(db)
    assert "FROM rag_drive_sources s" in sql
    assert "FROM rag_mail_sources m" in sql
    assert "m.id = rag_documents.mail_source_id" in sql
