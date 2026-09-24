"""Drive push → targeted reindex of linked trees, bounded (ADR-261 P2, ADR-304).

What production measured on 2026-09-22, each pinned here:

- the token a wake drained from was the QUEUED payload's, captured while the
  previous drain was still running — so every drain replayed the one before
  (22 minutes); the channel's own token is now the only authority;
- the drain held a PostgreSQL transaction for its whole length
  (``idle in transaction`` on ``webhook_channels``); nothing is held now while
  Google answers;
- the drain had no bound; it now stops, keeps its place, re-queues itself, and
  after a streak of truncated wakes rebases the feed and re-synchronises the
  linked trees in full;
- the downloads and embeddings ran INSIDE the wake sweep; they now run under
  the source's own lease, outside it.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator, Coroutine
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME, RAG_DRIVE_MAX_FILES_PER_SYNC
from src.domains.rag_spaces import drive_push
from src.domains.rag_spaces.drive_ingest import IngestResult, is_supported_drive_file

pytestmark = pytest.mark.unit


class _Sessions:
    """Fake ``get_db_context``: counts the sessions open at any instant."""

    def __init__(self) -> None:
        self.open = 0
        self.opened = 0

    @contextlib.asynccontextmanager
    async def __call__(self) -> AsyncIterator[MagicMock]:
        self.open += 1
        self.opened += 1
        try:
            db = MagicMock()
            db.commit = AsyncMock()
            db.rollback = AsyncMock()
            yield db
        finally:
            self.open -= 1


class _Redis:
    """Just enough Redis for the truncation streak and the wake queue."""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, _ttl: int) -> bool:
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


def _source(folder_id: str, folder_ids: list[str] | None = None) -> MagicMock:
    source = MagicMock()
    source.id = uuid.uuid4()
    source.space_id = uuid.uuid4()
    source.folder_id = folder_id
    source.folder_ids = list(folder_ids or [])
    source.synced_file_count = 3
    return source


def _change(
    file_id: str,
    parent: str,
    *,
    removed: bool = False,
    trashed: bool = False,
    mime_type: str = "text/plain",
) -> dict[str, Any]:
    return {
        "fileId": file_id,
        "removed": removed,
        "file": {
            "id": file_id,
            "name": f"{file_id}.txt",
            "mimeType": mime_type,
            "modifiedTime": "2026-09-03T10:00:00Z",
            "parents": [parent],
            "trashed": trashed,
        },
    }


class _Harness:
    """Every boundary of the push reindex, faked at the module's seams."""

    def __init__(
        self,
        *,
        sources: list[MagicMock],
        pages: list[dict[str, Any]],
        channel_token: str | None = "t0",
        lock: bool = True,
        credentials: object | None = None,
    ) -> None:
        self.sessions = _Sessions()
        self.redis = _Redis()
        self.sources = {s.id: s for s in sources}
        self.channel = MagicMock(id=uuid.uuid4(), page_token=channel_token)
        self.fired: list[Coroutine[Any, Any, Any]] = []
        self.list_pages_seen_open: list[int] = []

        async def _list_changes(token: str, page_size: int = 0) -> dict[str, Any]:
            self.list_pages_seen_open.append(self.sessions.open)
            return pages.pop(0)

        self.client = MagicMock()
        self.client.list_changes = AsyncMock(side_effect=_list_changes)
        self.client.get_changes_start_page_token = AsyncMock(return_value="fresh")
        self.client.close = AsyncMock()

        self.source_repo = MagicMock()
        self.source_repo.get_all_for_user = AsyncMock(return_value=sources)
        self.source_repo.get_by_id = AsyncMock(side_effect=lambda sid: self.sources.get(sid))

        async def _apply_update(source: MagicMock, payload: dict[str, Any]) -> MagicMock:
            for key, value in payload.items():
                setattr(source, key, value)
            return source

        self.source_repo.update = AsyncMock(side_effect=_apply_update)
        self.channel_repo = MagicMock()
        self.channel_repo.get_for_user = AsyncMock(return_value=self.channel)
        self.channel_repo.advance_page_token = AsyncMock(return_value=True)

        service = MagicMock()
        service.get_connector_credentials = AsyncMock(
            return_value=credentials if credentials is not None else {"token": "x"}
        )
        sessions = self.sessions

        class _Detached:
            @contextlib.asynccontextmanager
            async def unit_of_work(self) -> AsyncIterator[MagicMock]:
                async with sessions() as db:
                    service.db = db
                    yield service

        self.sync_service = MagicMock()
        self.sync_service.try_acquire_sync_lock = AsyncMock(return_value=lock)
        self.jobs = MagicMock()
        self.jobs.heartbeat_source = AsyncMock(return_value=True)
        self.full_sync = AsyncMock()
        self.enqueue = AsyncMock(return_value=True)
        self.ingest = AsyncMock(return_value=IngestResult("queued", {"document_id": uuid.uuid4()}))
        self.remove = AsyncMock(return_value=True)
        self.process = AsyncMock(return_value=(1, 0))

        def _fire(coro: Coroutine[Any, Any, Any], **_kwargs: Any) -> MagicMock:
            self.fired.append(coro)
            return MagicMock()

        self.reads: list[str] = []

        @contextlib.asynccontextmanager
        async def _space_read(*, user_id: object, section: str) -> AsyncIterator[None]:
            self.reads.append(section)
            yield

        self.patches = [
            patch.object(drive_push, "get_db_context", self.sessions),
            patch.object(drive_push, "DetachedConnectorService", _Detached),
            patch.object(drive_push, "RAGDriveSourceRepository", return_value=self.source_repo),
            patch.object(drive_push, "PushChannelRepository", return_value=self.channel_repo),
            patch.object(drive_push, "GoogleDriveClient", return_value=self.client),
            patch.object(drive_push, "RAGDriveSyncService", return_value=self.sync_service),
            patch.object(drive_push, "RAGJobsRepository", return_value=self.jobs),
            patch.object(drive_push, "safe_fire_and_forget", _fire),
            patch.object(drive_push, "sync_folder_background", self.full_sync),
            patch.object(drive_push, "enqueue_wake", self.enqueue),
            patch.object(drive_push, "get_redis_cache", AsyncMock(return_value=self.redis)),
            patch.object(drive_push, "ingest_drive_file", self.ingest),
            patch.object(drive_push, "remove_drive_document", self.remove),
            patch.object(drive_push, "process_queued", self.process),
            patch.object(drive_push, "space_read", _space_read),
        ]

    async def run(self, user_id: uuid.UUID | None = None) -> str:
        with contextlib.ExitStack() as stack:
            for p in self.patches:
                stack.enter_context(p)
            outcome = await drive_push.reindex_from_push(user_id or uuid.uuid4())
            # The test double owns what was fired: it runs it, like the loop would.
            for coro in self.fired:
                await coro
        return outcome


def _page(changes: list[dict[str, Any]], *, next_token: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"changes": changes}
    if next_token:
        body["nextPageToken"] = next_token
    else:
        body["newStartPageToken"] = "t1"
    return body


# ============================================================================
# Authority, sessions, and the fast paths
# ============================================================================


async def test_no_linked_folder_touches_nothing() -> None:
    harness = _Harness(sources=[], pages=[])
    assert await harness.run() == "no_linked_folder"
    harness.client.list_changes.assert_not_awaited()


async def test_a_channel_without_a_token_drains_nothing() -> None:
    harness = _Harness(sources=[_source("root")], pages=[], channel_token=None)
    assert await harness.run() == "no_linked_folder"
    harness.client.list_changes.assert_not_awaited()


async def test_the_feed_is_read_from_the_channels_own_token() -> None:
    """The channel row is the authority: a queued payload carries no token any more."""
    harness = _Harness(sources=[_source("root")], pages=[_page([])], channel_token="t42")
    await harness.run()
    assert harness.client.list_changes.await_args_list[0].args[0] == "t42"


async def test_no_session_is_open_while_google_answers() -> None:
    pages = [_page([], next_token="p1"), _page([_change("f1", "root")])]
    harness = _Harness(sources=[_source("root", ["root"])], pages=pages)
    await harness.run()
    assert harness.list_pages_seen_open == [0, 0]


async def test_one_wake_is_one_consultation_whatever_its_pages() -> None:
    """The register names the act, never the call (ADR-263)."""
    pages = [_page([], next_token="p1"), _page([], next_token="p2"), _page([])]
    harness = _Harness(sources=[_source("root", ["root"])], pages=pages)
    await harness.run()
    assert harness.reads == ["drive"]


# ============================================================================
# Handing the window over, then moving the token
# ============================================================================


async def test_changes_under_a_linked_tree_are_applied_and_the_token_advances() -> None:
    source = _source("root", ["root"])
    changes = [
        _change("f1", "root"),
        _change("f2", "elsewhere"),
        _change("f3", "root", trashed=True),
        _change("f4", "root", removed=True),
    ]
    harness = _Harness(sources=[source], pages=[_page(changes)])
    assert await harness.run() == "reindexed"
    assert [c.kwargs["drive_file"]["id"] for c in harness.ingest.await_args_list] == ["f1"]
    assert sorted(c.kwargs["file_id"] for c in harness.remove.await_args_list) == ["f3", "f4"]
    harness.process.assert_awaited_once()
    harness.channel_repo.advance_page_token.assert_awaited_once_with(
        harness.channel.id, expected="t0", new="t1"
    )
    assert source.sync_status == "completed"


async def test_the_apply_runs_outside_the_wake_under_the_sources_lease() -> None:
    """The sweep hands the window over; downloads and embeddings run in a task of their own."""
    harness = _Harness(sources=[_source("root", ["root"])], pages=[_page([_change("f1", "root")])])
    with contextlib.ExitStack() as stack:
        for p in harness.patches:
            stack.enter_context(p)
        await drive_push.reindex_from_push(uuid.uuid4())
        harness.ingest.assert_not_awaited()
        assert len(harness.fired) == 1
        harness.sync_service.try_acquire_sync_lock.assert_awaited_once()
        await harness.fired.pop()
    harness.ingest.assert_awaited_once()


async def test_a_tree_already_syncing_holds_the_token_and_requeues_the_wake() -> None:
    """Moving the token past a refused window LOST it; it is replayed instead."""
    harness = _Harness(
        sources=[_source("root", ["root"])], pages=[_page([_change("f1", "root")])], lock=False
    )
    user_id = uuid.uuid4()
    assert await harness.run(user_id) == "locked"
    harness.ingest.assert_not_awaited()
    harness.channel_repo.advance_page_token.assert_not_awaited()
    harness.enqueue.assert_awaited_once()
    assert harness.enqueue.await_args.args[1:3] == (user_id, "google_drive")


async def test_a_tree_that_refuses_holds_the_token_even_when_another_took_its_window() -> None:
    free, busy = _source("a", ["a"]), _source("b", ["b"])
    harness = _Harness(
        sources=[free, busy], pages=[_page([_change("f1", "a"), _change("f2", "b")])]
    )
    harness.sync_service.try_acquire_sync_lock = AsyncMock(side_effect=lambda sid: sid == free.id)
    assert await harness.run() == "locked"
    harness.channel_repo.advance_page_token.assert_not_awaited()
    # The tree that took its window applies it; the replay will skip what is unchanged.
    assert [c.kwargs["drive_file"]["id"] for c in harness.ingest.await_args_list] == ["f1"]


async def test_a_source_unlinked_before_its_apply_is_not_called_locked() -> None:
    source = _source("root", ["root"])
    harness = _Harness(sources=[source], pages=[_page([_change("f1", "root")])], lock=False)
    harness.sources.clear()
    assert await harness.run() == "no_linked_folder"


async def test_an_apply_failure_releases_the_source_as_error() -> None:
    source = _source("root", ["root"])
    harness = _Harness(sources=[source], pages=[_page([_change("f1", "root")])])
    harness.process.side_effect = RuntimeError("embedding provider down")
    assert await harness.run() == "reindexed"
    assert source.sync_status == "error"
    assert source.lease_expires_at is None
    harness.client.close.assert_awaited()


async def test_the_apply_ends_its_reads_before_the_embeddings() -> None:
    """A last change that only READ (a removal of nothing) leaves no transaction to embed under."""
    source = _source("root", ["root"])
    harness = _Harness(sources=[source], pages=[_page([_change("f4", "root", removed=True)])])
    order: list[str] = []
    harness.remove.side_effect = lambda *a, **k: order.append("read") or False
    harness.process.side_effect = lambda *a, **k: order.append("embed") or (0, 0)
    real_sessions = harness.sessions

    @contextlib.asynccontextmanager
    async def _sessions() -> AsyncIterator[MagicMock]:
        async with real_sessions() as db:
            db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
            yield db

    harness.patches[0] = patch.object(drive_push, "get_db_context", _sessions)
    await harness.run()
    assert order.index("commit") < order.index("embed")


async def test_a_tree_larger_than_a_full_sync_is_re_synchronised_in_full() -> None:
    """More routed changes than one synchronisation indexes: the walk reconciles, bounded."""
    source = _source("root", ["root"])
    changes = [_change(f"f{i}", "root") for i in range(RAG_DRIVE_MAX_FILES_PER_SYNC + 1)]
    harness = _Harness(sources=[source], pages=[_page(changes)])
    assert await harness.run() == "reindexed"
    harness.ingest.assert_not_awaited()
    harness.full_sync.assert_awaited_once_with(source.space_id, source.id, ANY)


# ============================================================================
# Bounds: truncation, re-queue, and the rebase breaker
# ============================================================================


async def test_a_truncated_drain_keeps_its_place_and_requeues_itself() -> None:
    pages = [_page([], next_token=f"p{i}") for i in range(settings.rag_drive_push_max_pages)]
    harness = _Harness(sources=[_source("root", ["root"])], pages=pages)
    user_id = uuid.uuid4()
    await harness.run(user_id)
    harness.channel_repo.advance_page_token.assert_awaited_once_with(
        harness.channel.id, expected="t0", new=f"p{settings.rag_drive_push_max_pages - 1}"
    )
    harness.enqueue.assert_awaited_once()
    assert harness.enqueue.await_args.args[1:3] == (user_id, "google_drive")
    assert list(harness.redis.values.values()) == [1]


async def test_a_drained_feed_resets_the_truncation_streak() -> None:
    harness = _Harness(sources=[_source("root", ["root"])], pages=[_page([])])
    user_id = uuid.uuid4()
    harness.redis.values[f"rag:drive_push:truncations:{user_id}"] = 3
    await harness.run(user_id)
    assert harness.redis.values == {}
    harness.enqueue.assert_not_awaited()


async def test_a_streak_of_truncations_rebases_the_feed_and_resyncs_in_full() -> None:
    limit = settings.rag_drive_push_max_consecutive_truncations
    pages = [
        _page([_change("f1", "root")], next_token=f"p{i}")
        for i in range(settings.rag_drive_push_max_pages)
    ]
    sources = [_source("root", ["root"]), _source("other", ["other"])]
    harness = _Harness(sources=sources, pages=pages)
    user_id = uuid.uuid4()
    harness.redis.values[f"rag:drive_push:truncations:{user_id}"] = limit - 1
    assert await harness.run(user_id) == "rebased"
    harness.channel_repo.advance_page_token.assert_awaited_once_with(
        harness.channel.id, expected="t0", new="fresh"
    )
    assert harness.full_sync.await_count == 2
    harness.ingest.assert_not_awaited()
    harness.enqueue.assert_not_awaited()
    assert harness.redis.values == {}


async def test_a_rebase_reads_the_start_token_before_any_synchronisation_starts() -> None:
    """Changes made between the token read and a walk are in the feed from that token."""
    pages = [_page([], next_token=f"p{i}") for i in range(settings.rag_drive_push_max_pages)]
    harness = _Harness(sources=[_source("root", ["root"])], pages=pages)
    user_id = uuid.uuid4()
    harness.redis.values[f"rag:drive_push:truncations:{user_id}"] = (
        settings.rag_drive_push_max_consecutive_truncations - 1
    )
    order: list[str] = []
    harness.client.get_changes_start_page_token.side_effect = (
        lambda: order.append("token") or "fresh"
    )
    harness.sync_service.try_acquire_sync_lock.side_effect = (
        lambda _sid: order.append("lock") or True
    )
    assert await harness.run(user_id) == "rebased"
    assert order == ["token", "lock"]


async def test_a_rebase_with_a_tree_still_syncing_holds_the_token() -> None:
    pages = [_page([], next_token=f"p{i}") for i in range(settings.rag_drive_push_max_pages)]
    harness = _Harness(sources=[_source("root", ["root"])], pages=pages, lock=False)
    user_id = uuid.uuid4()
    limit = settings.rag_drive_push_max_consecutive_truncations
    harness.redis.values[f"rag:drive_push:truncations:{user_id}"] = limit - 1
    assert await harness.run(user_id) == "locked"
    harness.channel_repo.advance_page_token.assert_not_awaited()
    harness.enqueue.assert_awaited_once()
    # The streak is kept: the next wake tries the rebase again.
    assert list(harness.redis.values.values()) == [limit]


async def test_a_feed_error_is_counted_and_moves_nothing() -> None:
    harness = _Harness(sources=[_source("root", ["root"])], pages=[{"changes": []}])
    assert await harness.run() == "error"
    harness.channel_repo.advance_page_token.assert_not_awaited()
    harness.client.close.assert_awaited()


# ============================================================================
# Routing a TREE (ADR-297), preserved across the pages of one drain
# ============================================================================


async def test_a_change_in_a_sub_folder_of_the_linked_tree_is_applied() -> None:
    source = _source("root", ["root", "sub1"])
    harness = _Harness(
        sources=[source], pages=[_page([_change("f1", "sub1"), _change("f2", "elsewhere")])]
    )
    assert await harness.run() == "reindexed"
    assert [c.kwargs["drive_file"]["id"] for c in harness.ingest.await_args_list] == ["f1"]


async def test_a_new_sub_folder_is_persisted_as_a_new_list() -> None:
    source = _source("root", ["root"])
    before = source.folder_ids
    pages = [
        _page([_change("newsub", "root", mime_type=GOOGLE_DRIVE_FOLDER_MIME)], next_token="p1"),
        _page([_change("f9", "newsub")]),
    ]
    harness = _Harness(sources=[source], pages=pages)
    assert await harness.run() == "reindexed"
    assert [c.kwargs["drive_file"]["id"] for c in harness.ingest.await_args_list] == ["f9"]
    assert "newsub" in source.folder_ids
    assert source.folder_ids is not before


async def test_a_trashed_sub_folder_leaves_the_routing_set() -> None:
    source = _source("root", ["root", "sub1"])
    pages = [_page([_change("sub1", "root", mime_type=GOOGLE_DRIVE_FOLDER_MIME, trashed=True)])]
    harness = _Harness(sources=[source], pages=pages)
    await harness.run()
    assert source.folder_ids == ["root"]
    harness.ingest.assert_not_awaited()


def test_supported_drive_file_uses_the_shared_maps() -> None:
    assert is_supported_drive_file({"mimeType": "text/plain"}) is True
    assert is_supported_drive_file({"mimeType": "video/mp4"}) is False


# ============================================================================
# One file: the download never runs inside a transaction
# ============================================================================


async def test_an_ingestion_ends_its_reads_before_the_download() -> None:
    """The reads decide, their transaction ends, THEN Google is called (ADR-304)."""
    from src.domains.rag_spaces import drive_ingest

    order: list[str] = []
    db = MagicMock()
    db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
    client = MagicMock()
    client.get_file_content = AsyncMock(
        side_effect=lambda *a, **k: order.append("download") or b"x"
    )
    doc_repo = MagicMock()
    doc_repo.get_by_drive_file_id = AsyncMock(side_effect=lambda *a: order.append("read"))
    doc_repo.count_for_space = AsyncMock(return_value=0)
    with (
        patch.object(drive_ingest, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(
            drive_ingest, "create_pending_document", AsyncMock(return_value={"document_id": 1})
        ),
    ):
        result = await drive_ingest.ingest_drive_file(
            db,
            client,
            space_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            drive_file={"id": "f1", "name": "a.txt", "mimeType": "text/plain"},
        )
    assert result.outcome == "queued"
    assert order == ["read", "commit", "download"]
