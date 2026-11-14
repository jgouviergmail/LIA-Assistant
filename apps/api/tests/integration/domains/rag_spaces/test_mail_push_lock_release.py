"""A Gmail push pass returns the lock it took, on real PostgreSQL (ADR-262).

The push pass loads the label sources, takes each source's SYNCING lease with
one conditional SQL statement, applies Gmail's history, then releases the lease
through the repository. The lease is written by SQL the ORM never sees, so a
release computed from the row as it was loaded BEFORE the lease writes nothing
of what it means to: the source stays SYNCING, its lease expires, and the
reaper replays a full label sync after every push (measured in production on
2026-11-10: 236 replays and 127,585 thread reads in 24 hours).

The unit tests mock the lease, so only a real database can hold this. Gmail
itself is not exercised: the client is a double, and embedding is mocked.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces import mail_sync
from src.domains.rag_spaces.drive_ingest import IngestResult
from src.domains.rag_spaces.jobs_repository import MAIL_SOURCE_TABLE, RAGJobsRepository
from src.domains.rag_spaces.models import RAGMailSource, RAGSourceSyncStatus, RAGSpace
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

_LABEL = "Label_42"
_ANCHOR_BEFORE = 100
_ANCHOR_AFTER = 200


class _GmailDouble:
    """The three calls the incremental path makes, answered from memory."""

    def __init__(self, history: list[dict[str, Any]]) -> None:
        self._history = history
        self.closed = False

    async def get_history(self, start_history_id: str, **_: Any) -> dict[str, Any]:
        assert start_history_id == str(_ANCHOR_BEFORE)
        return {"history": self._history, "historyId": str(_ANCHOR_AFTER)}

    async def get_thread(self, thread_id: str, **_: Any) -> dict[str, Any]:
        return {"id": thread_id, "messages": [{"id": "m1", "labelIds": [_LABEL]}]}

    async def close(self) -> None:
        self.closed = True


async def _make_source(db: AsyncSession, *, label_id: str = _LABEL) -> RAGMailSource:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    space = RAGSpace(name="mail-push-test", user_id=user.id)
    db.add(space)
    await db.flush()
    source = RAGMailSource(
        space_id=space.id,
        user_id=user.id,
        label_id=label_id,
        label_name="Kept",
        sync_status=RAGSourceSyncStatus.COMPLETED,
        last_history_id=_ANCHOR_BEFORE,
    )
    db.add(source)
    await db.commit()
    return source


async def _row(db: AsyncSession, source_id: uuid.UUID) -> dict[str, Any]:
    """The row as PostgreSQL holds it, read past the ORM's identity map."""
    result = await db.execute(
        text(
            "SELECT sync_status, attempts, lease_expires_at, worker_id, heartbeat_at, "
            "last_history_id, last_sync_at FROM rag_mail_sources WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    status, attempts, lease, worker, heartbeat, anchor, last_sync = result.one()
    return {
        "status": status,
        "attempts": attempts,
        "lease": lease,
        "worker": worker,
        "heartbeat": heartbeat,
        "anchor": anchor,
        "last_sync": last_sync,
    }


def _serve_pushes_on(
    monkeypatch: pytest.MonkeyPatch, db: AsyncSession, client: _GmailDouble
) -> None:
    """Run the push pass on the test's session, with the Gmail double."""

    @asynccontextmanager
    async def _context() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr(mail_sync, "get_db_context", _context)
    monkeypatch.setattr(mail_sync, "gmail_client_or_none", AsyncMock(return_value=client))


async def test_a_push_with_nothing_new_returns_the_lock(
    monkeypatch: pytest.MonkeyPatch, async_session: AsyncSession
) -> None:
    source = await _make_source(async_session)
    client = _GmailDouble(history=[])
    _serve_pushes_on(monkeypatch, async_session, client)

    outcome = await mail_sync.index_mail_sources_from_push(source.user_id)

    assert outcome == "nothing"
    row = await _row(async_session, source.id)
    assert row["status"] == RAGSourceSyncStatus.COMPLETED
    assert row["lease"] is None
    assert row["worker"] is None
    assert row["heartbeat"] is None
    assert row["attempts"] == 0
    assert row["anchor"] == _ANCHOR_AFTER
    assert row["last_sync"] is not None
    assert client.closed is True


async def test_the_reaper_has_nothing_to_recover_after_a_push(
    monkeypatch: pytest.MonkeyPatch, async_session: AsyncSession
) -> None:
    source = await _make_source(async_session)
    _serve_pushes_on(monkeypatch, async_session, _GmailDouble(history=[]))

    await mail_sync.index_mail_sources_from_push(source.user_id)
    # Five minutes later: any lease the pass left behind has expired.
    await async_session.execute(
        text(
            "UPDATE rag_mail_sources SET lease_expires_at = now() - interval '1 hour' "
            "WHERE id = :id AND lease_expires_at IS NOT NULL"
        ),
        {"id": str(source.id)},
    )
    await async_session.commit()

    recoverable = await RAGJobsRepository(async_session).fetch_recoverable_sources(
        limit=100, table=MAIL_SOURCE_TABLE
    )
    assert source.id not in recoverable


async def test_a_push_that_indexes_a_thread_returns_the_lock_and_advances_the_anchor(
    monkeypatch: pytest.MonkeyPatch, async_session: AsyncSession
) -> None:
    source = await _make_source(async_session)
    history = [
        {"messagesAdded": [{"message": {"id": "m1", "threadId": "t1", "labelIds": [_LABEL]}}]}
    ]
    _serve_pushes_on(monkeypatch, async_session, _GmailDouble(history=history))
    queued = {"document_id": uuid.uuid4()}
    ingest = AsyncMock(return_value=IngestResult("queued", queued))
    embed = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr(mail_sync, "ingest_thread", ingest)
    monkeypatch.setattr(mail_sync, "process_queued", embed)

    outcome = await mail_sync.index_mail_sources_from_push(source.user_id)

    assert outcome == "indexed"
    assert ingest.await_args.kwargs["thread_id"] == "t1"
    assert embed.await_args.args[0] == [queued]
    row = await _row(async_session, source.id)
    assert row["status"] == RAGSourceSyncStatus.COMPLETED
    assert row["lease"] is None
    assert row["attempts"] == 0
    assert row["anchor"] == _ANCHOR_AFTER


async def test_every_source_of_the_account_is_released(
    monkeypatch: pytest.MonkeyPatch, async_session: AsyncSession
) -> None:
    first = await _make_source(async_session)
    second = RAGMailSource(
        space_id=first.space_id,
        user_id=first.user_id,
        label_id="Label_43",
        label_name="Also kept",
        sync_status=RAGSourceSyncStatus.COMPLETED,
        last_history_id=_ANCHOR_BEFORE,
    )
    async_session.add(second)
    await async_session.commit()
    _serve_pushes_on(monkeypatch, async_session, _GmailDouble(history=[]))

    await mail_sync.index_mail_sources_from_push(first.user_id)

    for source in (first, second):
        row = await _row(async_session, source.id)
        assert row["status"] == RAGSourceSyncStatus.COMPLETED
        assert row["lease"] is None
