"""The reaper recovers a crashed label sync like a crashed Drive sync (ADR-262)."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.rag_spaces import reapers

pytestmark = pytest.mark.unit


@contextlib.asynccontextmanager
async def _db_with(source: object):  # type: ignore[no-untyped-def]
    db = AsyncMock()
    db.get = AsyncMock(return_value=source)
    yield db


async def test_a_stuck_label_sync_is_released_and_redriven(monkeypatch: pytest.MonkeyPatch) -> None:
    source = MagicMock()
    source.user_id = uuid.uuid4()
    source_id = uuid.uuid4()
    jobs = MagicMock()
    jobs.reclaim_or_fail_source = AsyncMock(return_value="syncing")
    redrive = AsyncMock()
    with (
        patch.object(reapers, "get_db_context", lambda: _db_with(source)),
        patch.object(reapers, "RAGJobsRepository", return_value=jobs),
        patch("src.domains.rag_spaces.mail_sync.sync_label_background", redrive),
    ):
        outcome = await reapers._recover_mail_source(source_id, asyncio.Semaphore(1))
    assert outcome == "requeued"
    assert jobs.reclaim_or_fail_source.await_args.kwargs["table"] == "rag_mail_sources"
    redrive.assert_awaited_once_with(source_id=source_id, user_id=source.user_id)


async def test_an_exhausted_label_sync_is_dead_lettered() -> None:
    source = MagicMock()
    source.user_id = uuid.uuid4()
    jobs = MagicMock()
    jobs.reclaim_or_fail_source = AsyncMock(return_value="error")
    with (
        patch.object(reapers, "get_db_context", lambda: _db_with(source)),
        patch.object(reapers, "RAGJobsRepository", return_value=jobs),
        patch("src.domains.rag_spaces.mail_sync.sync_label_background", AsyncMock()) as redrive,
    ):
        outcome = await reapers._recover_mail_source(uuid.uuid4(), asyncio.Semaphore(1))
    assert outcome == "failed"
    redrive.assert_not_awaited()


async def test_the_sweep_reads_the_mail_table() -> None:
    jobs = MagicMock()
    jobs.fetch_recoverable_sources = AsyncMock(return_value=[])
    with (
        patch.object(reapers, "get_db_context", lambda: _db_with(None)),
        patch.object(reapers, "RAGJobsRepository", return_value=jobs),
    ):
        await reapers._recover_mail_sources(asyncio.Semaphore(1))
    assert jobs.fetch_recoverable_sources.await_args.kwargs["table"] == "rag_mail_sources"
