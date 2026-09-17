"""A kept answer is projected into the « Kept answers » knowledge space (2026-09-16, part A).

What this pins:

- the rendering is PURE and dated: title, quoted request (or the notification
  line), the answer verbatim — an HTML ``lia-response`` converted by the
  pipeline's own helper;
- the display name is the person's request, sanitised like a mail subject;
- the exposed state is DERIVED from the document while it exists;
- the space is found by ROLE, created once in the person's language;
- a projection is CLAIMED before any effect, so a click and the sweep never
  create two documents; every gate leaves a terminal, honest state;
- discarding a bookmark discards its projection in the caller's transaction;
- the reconciliation is bounded and never retries a dead-lettered projection.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.constants import BOOKMARKS_SPACE_KIND
from src.domains.bookmarks import indexing
from src.domains.bookmarks.indexing import (
    discard_index,
    document_name,
    ensure_bookmarks_space,
    index_bookmark,
    reconcile_bookmark_index,
    render_bookmark,
)
from src.domains.bookmarks.models import BookmarkIndexState
from src.domains.bookmarks.projection import derived_index_state, index_usage_of
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.models import RAGDocumentStatus

pytestmark = pytest.mark.unit

BACKSLASH = chr(92)
ANSWERED = datetime(2026, 9, 12, 8, 30, tzinfo=UTC)


def _bookmark(**overrides: Any) -> SimpleNamespace:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content="**Réservé** : salle B, 14 h.",
        request_content="Réserve la salle B à 14 h\nmerci",
        answered_at=ANSWERED,
        rag_document_id=None,
        index_state=None,
        indexed_at=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


# ---------------------------------------------------------------------------
# Rendering (pure)
# ---------------------------------------------------------------------------


class TestRenderBookmark:
    def test_the_document_is_dated_quotes_the_request_and_keeps_the_answer(self) -> None:
        text = render_bookmark(_bookmark(), language="fr", timezone="Europe/Paris")
        lines = text.splitlines()
        assert lines[0].startswith("# Réponse conservée du ")
        assert "12 septembre 2026" in lines[0]
        assert "> Réserve la salle B à 14 h" in lines and "> merci" in lines
        assert "**Réservé** : salle B, 14 h." in text
        assert "Répondu le" in text and "10:30" in text  # Paris is UTC+2 in September

    def test_a_notification_carries_the_no_request_line_instead_of_a_quote(self) -> None:
        text = render_bookmark(_bookmark(request_content=None), language="en", timezone="UTC")
        assert "Kept from a notification LIA sent on its own initiative" in text
        assert ">" not in text.split("\n", 2)[2].split("Answered on")[0]

    def test_an_html_answer_is_converted_and_scripts_never_reach_the_text(self) -> None:
        html = (
            '<div class="lia-response"><script>alert(1)</script>'
            "<h2>Plan</h2><p>Deux <b>options</b></p></div>"
        )
        text = render_bookmark(_bookmark(content=html), language="en", timezone="UTC")
        assert "<div" not in text and "alert(1)" not in text
        assert "Plan" in text and "options" in text

    def test_markdown_with_angle_brackets_is_left_verbatim(self) -> None:
        answer = "Use `vector<int> v;` and `map<string, int> m;` here."
        text = render_bookmark(_bookmark(content=answer), language="en", timezone="UTC")
        assert answer in text


class TestDocumentName:
    def test_the_name_carries_the_date_and_a_bounded_sanitised_excerpt(self) -> None:
        hostile = 'Re: "urgent"\r\nX: 1\tand /etc/passwd' + BACKSLASH + "..\x00" + "x" * 500
        name = document_name(_bookmark(request_content=hostile), language="en", timezone="UTC")
        assert name.endswith(".md")
        assert "\r" not in name and "\n" not in name and "/" not in name
        assert BACKSLASH not in name and "\x00" not in name
        assert "2026-09-12" in name
        assert len(name) < 120

    def test_a_notification_is_named_by_its_date_alone(self) -> None:
        name = document_name(_bookmark(request_content=None), language="fr", timezone="UTC")
        assert name == "Réponse conservée 2026-09-12.md"


# ---------------------------------------------------------------------------
# Derived state and usage
# ---------------------------------------------------------------------------


class TestDerivedState:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (RAGDocumentStatus.READY, "indexed"),
            (RAGDocumentStatus.ERROR, "error"),
            (RAGDocumentStatus.PENDING, "pending"),
            (RAGDocumentStatus.PROCESSING, "pending"),
            (RAGDocumentStatus.REINDEXING, "pending"),
        ],
    )
    def test_the_document_is_the_authority_while_it_exists(
        self, status: str, expected: str
    ) -> None:
        row = _bookmark(index_state="deferred", rag_document_id=uuid.uuid4())
        assert derived_index_state(row, SimpleNamespace(status=status)) == expected

    def test_without_a_document_the_stored_reason_answers(self) -> None:
        assert derived_index_state(_bookmark(index_state="deferred"), None) == "deferred"
        assert derived_index_state(_bookmark(), None) is None


class TestIndexUsage:
    def test_a_ready_document_reports_its_embedding_cost(self) -> None:
        document = SimpleNamespace(
            status=RAGDocumentStatus.READY,
            embedding_tokens=812,
            embedding_cost_eur=0.000123,
            embedding_model="gemini-embedding-001",
        )
        usage = index_usage_of(document)
        assert usage is not None
        assert (usage.tokens_in, usage.tokens_out, usage.tokens_cache) == (812, 0, 0)
        assert usage.cost_eur == pytest.approx(0.000123)
        assert usage.model_name == "gemini-embedding-001"

    def test_nothing_is_claimed_before_the_document_is_ready(self) -> None:
        assert index_usage_of(None) is None
        assert index_usage_of(SimpleNamespace(status=RAGDocumentStatus.PENDING)) is None


# ---------------------------------------------------------------------------
# The space, found by role
# ---------------------------------------------------------------------------


def _space_repo(existing: Any = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_kind_for_user.return_value = existing
    return repo


async def test_an_existing_space_is_returned_without_creating_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = SimpleNamespace(id=uuid.uuid4(), kind=BOOKMARKS_SPACE_KIND)
    repo = _space_repo(space)
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    assert await ensure_bookmarks_space(AsyncMock(), uuid.uuid4(), "fr") is space
    repo.create.assert_not_awaited()


async def test_the_space_is_created_in_the_users_language_with_the_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = SimpleNamespace(id=uuid.uuid4())
    repo = _space_repo(None)
    repo.create.return_value = created
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    db = AsyncMock()
    assert await ensure_bookmarks_space(db, uuid.uuid4(), "fr") is created
    payload = repo.create.call_args.args[0]
    assert payload["name"] == "Réponses conservées" and payload["kind"] == BOOKMARKS_SPACE_KIND
    assert payload["is_active"] is True and payload["is_system"] is False
    assert payload["description"]
    db.commit.assert_awaited_once()


async def test_a_lost_race_on_the_kind_returns_the_winners_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    winner = SimpleNamespace(id=uuid.uuid4())
    repo = AsyncMock()
    repo.get_by_kind_for_user.side_effect = [None, winner]
    repo.create.side_effect = IntegrityError("insert", {}, Exception("dup"))
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    db = AsyncMock()
    assert await ensure_bookmarks_space(db, uuid.uuid4(), "en") is winner
    db.rollback.assert_awaited_once()


async def test_a_name_clash_with_a_hand_made_space_is_suffixed_never_adopted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = SimpleNamespace(id=uuid.uuid4())
    repo = AsyncMock()
    repo.get_by_kind_for_user.return_value = None
    repo.create.side_effect = [IntegrityError("insert", {}, Exception("name")), created]
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    assert await ensure_bookmarks_space(AsyncMock(), uuid.uuid4(), "en") is created
    names = [call.args[0]["name"] for call in repo.create.call_args_list]
    assert names == ["Kept answers", "Kept answers (2)"]


# ---------------------------------------------------------------------------
# index_bookmark — claim, gates, projection, settle
# ---------------------------------------------------------------------------


class _Harness:
    """Everything ``index_bookmark`` touches, stubbed at the module seams."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, bookmark: SimpleNamespace) -> None:
        self.bookmark = bookmark
        self.db = AsyncMock()
        self.bookmarks = AsyncMock()
        self.bookmarks.claim_for_projection.return_value = True
        self.bookmarks.get_for_user.return_value = bookmark
        self.bookmarks.get_by_id.return_value = bookmark
        self.users = AsyncMock()
        self.users.get_by_id.return_value = SimpleNamespace(
            id=bookmark.user_id, language="fr", timezone="Europe/Paris"
        )
        self.space = SimpleNamespace(id=uuid.uuid4(), kind=BOOKMARKS_SPACE_KIND)
        self.spaces = AsyncMock()
        self.spaces.get_by_kind_for_user.return_value = self.space
        self.document_id = uuid.uuid4()
        self.create_pending = AsyncMock(
            return_value={
                "document_id": self.document_id,
                "space_id": self.space.id,
                "user_id": bookmark.user_id,
                "filename": "abc.md",
                "original_filename": "Réponse conservée 2026-09-12 — Réserve.md",
                "content_type": "text/markdown",
            }
        )
        self.process = AsyncMock(return_value=True)
        self.capability = AsyncMock(return_value=True)
        self.spend_blocked = AsyncMock(return_value=False)
        self.settings = SimpleNamespace(
            rag_job_reaper_grace_seconds=120,
            rag_spaces_storage_path="/tmp/rag",
        )

        @asynccontextmanager
        async def _ctx():  # type: ignore[no-untyped-def]
            yield self.db

        monkeypatch.setattr(indexing, "get_db_context", _ctx)
        monkeypatch.setattr(indexing, "BookmarkRepository", lambda db: self.bookmarks)
        monkeypatch.setattr(indexing, "UserRepository", lambda db: self.users)
        monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: self.spaces)
        monkeypatch.setattr(indexing, "create_pending_document", self.create_pending)
        monkeypatch.setattr(indexing, "process_document", self.process)
        monkeypatch.setattr(indexing, "is_capability_enabled", self.capability)
        monkeypatch.setattr(indexing, "spend_blocked", self.spend_blocked)
        monkeypatch.setattr(indexing, "settings", self.settings)

    def settled_state(self) -> str | None:
        calls = self.bookmarks.set_index_state.call_args_list
        return calls[-1].kwargs["state"] if calls else None


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    return _Harness(monkeypatch, _bookmark())


async def test_a_contended_claim_does_nothing_and_reads_no_gate(harness: _Harness) -> None:
    harness.bookmarks.claim_for_projection.return_value = False
    assert await index_bookmark(harness.bookmark.id) is False
    harness.capability.assert_not_awaited()
    harness.create_pending.assert_not_awaited()
    harness.bookmarks.set_index_state.assert_not_awaited()


@pytest.mark.parametrize("answers", [[False, True], [True, False]])
async def test_either_capability_off_settles_disabled_and_embeds_nothing(
    harness: _Harness, answers: list[bool]
) -> None:
    """RAG_SPACES and BOOKMARKS are both read AT CALL TIME (ceiling AND switch)."""
    harness.capability.side_effect = answers
    assert await index_bookmark(harness.bookmark.id) is False
    assert harness.settled_state() == BookmarkIndexState.DISABLED.value
    asked = {call.args[0] for call in harness.capability.call_args_list}
    assert {PlatformCapability.RAG_SPACES, PlatformCapability.BOOKMARKS} >= asked
    harness.create_pending.assert_not_awaited()
    harness.spend_blocked.assert_not_awaited()


async def test_a_blocked_spend_settles_deferred_and_embeds_nothing(harness: _Harness) -> None:
    harness.spend_blocked.return_value = True
    assert await index_bookmark(harness.bookmark.id) is False
    assert harness.settled_state() == BookmarkIndexState.DEFERRED.value
    harness.create_pending.assert_not_awaited()
    harness.process.assert_not_awaited()


async def test_a_successful_projection_is_indexed_and_dated(harness: _Harness) -> None:
    assert await index_bookmark(harness.bookmark.id) is True
    # The document was created under the role space with the rendered bytes.
    kwargs = harness.create_pending.call_args.kwargs
    assert kwargs["space_id"] == harness.space.id
    assert kwargs["user_id"] == harness.bookmark.user_id
    assert kwargs["content_type"] == "text/markdown"
    assert kwargs["source_fields"]["source_type"] == "bookmark"
    assert b"# R\xc3\xa9ponse conserv\xc3\xa9e du " in kwargs["content"]
    # The bookmark pointed at the document BEFORE processing, then settled.
    states = [c.kwargs for c in harness.bookmarks.set_index_state.call_args_list]
    assert states[0]["state"] == BookmarkIndexState.PENDING.value
    assert states[0]["rag_document_id"] == harness.document_id
    assert states[-1]["state"] == BookmarkIndexState.INDEXED.value
    assert states[-1]["indexed_at"] is not None
    harness.process.assert_awaited_once()
    assert harness.process.call_args.kwargs["document_id"] == harness.document_id


async def test_a_failed_processing_settles_error_and_keeps_the_document_link(
    harness: _Harness,
) -> None:
    harness.process.return_value = False
    assert await index_bookmark(harness.bookmark.id) is False
    assert harness.settled_state() == BookmarkIndexState.ERROR.value
    last = harness.bookmarks.set_index_state.call_args_list[-1].kwargs
    assert last["indexed_at"] is None


async def test_a_storage_failure_settles_error_without_raising(harness: _Harness) -> None:
    harness.create_pending.side_effect = OSError("disk full")
    assert await index_bookmark(harness.bookmark.id) is False
    assert harness.settled_state() == BookmarkIndexState.ERROR.value
    harness.process.assert_not_awaited()


async def test_a_link_that_fails_takes_the_created_document_back(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A committed document no bookmark points at would be an orphan the sweep
    would double: the projection takes it back before settling ``error``."""
    created = SimpleNamespace(
        id=harness.document_id,
        user_id=harness.bookmark.user_id,
        space_id=harness.space.id,
        filename="abc.md",
    )
    documents = AsyncMock()
    documents.get_by_id.return_value = created
    monkeypatch.setattr(indexing, "RAGDocumentRepository", lambda db: documents)
    # The path builder reads the REAL settings (document_access), not the
    # harness's stand-in.
    from src.domains.rag_spaces import document_access

    monkeypatch.setattr(document_access.settings, "rag_spaces_storage_path", str(tmp_path))
    stored = tmp_path / str(created.user_id) / str(created.space_id) / "abc.md"
    stored.parent.mkdir(parents=True)
    stored.write_text("x", encoding="utf-8")

    async def _link(*args: Any, **kwargs: Any) -> None:
        if kwargs.get("rag_document_id") is not None:
            raise RuntimeError("db gone")

    harness.bookmarks.set_index_state.side_effect = _link

    assert await index_bookmark(harness.bookmark.id) is False

    documents.delete.assert_awaited_once_with(created)
    assert not stored.exists()
    harness.process.assert_not_awaited()


async def test_a_bookmark_deleted_while_its_document_was_created_takes_it_back(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The second click lands between the document's commit and the link's.

    The link then updates NO row: without the take-back, the space would keep
    a document no bookmark points at — one the sweep cannot see (the bookmark
    is gone) and the person cannot delete (it is managed by role).
    """
    created = SimpleNamespace(
        id=harness.document_id,
        user_id=harness.bookmark.user_id,
        space_id=harness.space.id,
        filename="abc.md",
    )
    documents = AsyncMock()
    documents.get_by_id.return_value = created
    monkeypatch.setattr(indexing, "RAGDocumentRepository", lambda db: documents)
    from src.domains.rag_spaces import document_access

    monkeypatch.setattr(document_access.settings, "rag_spaces_storage_path", str(tmp_path))
    stored = tmp_path / str(created.user_id) / str(created.space_id) / "abc.md"
    stored.parent.mkdir(parents=True)
    stored.write_text("x", encoding="utf-8")
    harness.bookmarks.set_index_state.return_value = 0  # the row is gone

    assert await index_bookmark(harness.bookmark.id) is False

    documents.delete.assert_awaited_once_with(created)
    assert not stored.exists()
    harness.process.assert_not_awaited()
    # Nothing to settle on a row that no longer exists: the link was the last write.
    assert harness.bookmarks.set_index_state.await_count == 1


async def test_a_bookmark_that_vanished_after_the_claim_does_nothing(harness: _Harness) -> None:
    harness.bookmarks.get_by_id.return_value = None
    assert await index_bookmark(harness.bookmark.id) is False
    harness.create_pending.assert_not_awaited()


# ---------------------------------------------------------------------------
# discard_index — in the caller's transaction
# ---------------------------------------------------------------------------


async def test_discarding_deletes_the_chunks_and_the_row_and_hands_back_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), space_id=uuid.uuid4(), filename="doc.md"
    )
    documents = AsyncMock()
    documents.get_by_id.return_value = document
    chunks = AsyncMock()
    monkeypatch.setattr(indexing, "RAGDocumentRepository", lambda db: documents)
    monkeypatch.setattr(indexing, "RAGChunkRepository", lambda db: chunks)
    monkeypatch.setattr(indexing.settings, "rag_spaces_storage_path", str(tmp_path))
    db = AsyncMock()

    path = await discard_index(db, _bookmark(rag_document_id=document.id))

    chunks.delete_by_document.assert_awaited_once_with(document.id)
    documents.delete.assert_awaited_once_with(document)
    db.commit.assert_not_awaited()
    assert path == (tmp_path / str(document.user_id) / str(document.space_id) / "doc.md")


async def test_discarding_a_bookmark_without_projection_touches_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = AsyncMock()
    monkeypatch.setattr(indexing, "RAGDocumentRepository", lambda db: documents)
    assert await discard_index(AsyncMock(), _bookmark()) is None
    documents.get_by_id.assert_not_awaited()


async def test_a_dangling_reference_is_not_an_obstacle(monkeypatch: pytest.MonkeyPatch) -> None:
    documents = AsyncMock()
    documents.get_by_id.return_value = None
    monkeypatch.setattr(indexing, "RAGDocumentRepository", lambda db: documents)
    assert await discard_index(AsyncMock(), _bookmark(rag_document_id=uuid.uuid4())) is None


# ---------------------------------------------------------------------------
# Reconciliation — bounded, idempotent, never retrying a dead letter
# ---------------------------------------------------------------------------


async def test_the_sweep_projects_the_unprojected_under_bounded_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = [uuid.uuid4() for _ in range(5)]
    bookmarks = AsyncMock()
    bookmarks.unprojected_ids.return_value = ids
    monkeypatch.setattr(indexing, "BookmarkRepository", lambda db: bookmarks)

    @asynccontextmanager
    async def _ctx():  # type: ignore[no-untyped-def]
        yield AsyncMock()

    monkeypatch.setattr(indexing, "get_db_context", _ctx)
    in_flight = 0
    peak = 0
    outcomes = iter([True, True, False, True, False])

    async def _index(bookmark_id: uuid.UUID) -> bool:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return next(outcomes)

    monkeypatch.setattr(indexing, "index_bookmark", _index)
    monkeypatch.setattr(indexing, "is_capability_enabled", AsyncMock(return_value=True))

    counts = await reconcile_bookmark_index(limit=10, concurrency=2, grace_seconds=120)

    bookmarks.unprojected_ids.assert_awaited_once_with(limit=10, grace_seconds=120)
    assert counts == {"selected": 5, "indexed": 3, "not_indexed": 2}
    assert peak <= 2


async def test_a_capped_batch_is_said_not_silenced(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    bookmarks = AsyncMock()
    bookmarks.unprojected_ids.return_value = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(indexing, "BookmarkRepository", lambda db: bookmarks)

    @asynccontextmanager
    async def _ctx():  # type: ignore[no-untyped-def]
        yield AsyncMock()

    monkeypatch.setattr(indexing, "get_db_context", _ctx)
    monkeypatch.setattr(indexing, "index_bookmark", AsyncMock(return_value=True))
    monkeypatch.setattr(indexing, "is_capability_enabled", AsyncMock(return_value=True))
    logged = MagicMock()
    monkeypatch.setattr(indexing, "logger", logged)

    await reconcile_bookmark_index(limit=2, concurrency=1, grace_seconds=1)

    events = [call.args[0] for call in logged.info.call_args_list]
    assert "bookmark_reconcile_batch_capped" in events


async def test_a_switched_off_capability_skips_the_whole_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate is read ONCE per pass: a sweep over a disabled instance selects nothing.

    Otherwise every tick would claim, read the gate and rewrite ``disabled`` on
    up to ``limit`` rows — churn on every row of every account, for as long as
    the switch stays off.
    """
    bookmarks = AsyncMock()
    monkeypatch.setattr(indexing, "BookmarkRepository", lambda db: bookmarks)
    monkeypatch.setattr(indexing, "is_capability_enabled", AsyncMock(return_value=False))
    index = AsyncMock()
    monkeypatch.setattr(indexing, "index_bookmark", index)

    counts = await reconcile_bookmark_index(limit=5, concurrency=1, grace_seconds=1)

    assert counts == {"selected": 0, "indexed": 0, "not_indexed": 0}
    bookmarks.unprojected_ids.assert_not_awaited()
    index.assert_not_awaited()


async def test_an_empty_backlog_costs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    bookmarks = AsyncMock()
    bookmarks.unprojected_ids.return_value = []
    monkeypatch.setattr(indexing, "BookmarkRepository", lambda db: bookmarks)

    @asynccontextmanager
    async def _ctx():  # type: ignore[no-untyped-def]
        yield AsyncMock()

    monkeypatch.setattr(indexing, "get_db_context", _ctx)
    index = AsyncMock()
    monkeypatch.setattr(indexing, "index_bookmark", index)
    monkeypatch.setattr(indexing, "is_capability_enabled", AsyncMock(return_value=True))
    counts = await reconcile_bookmark_index(limit=5, concurrency=1, grace_seconds=1)
    assert counts == {"selected": 0, "indexed": 0, "not_indexed": 0}
    index.assert_not_awaited()
