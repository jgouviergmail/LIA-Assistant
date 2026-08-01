"""Relations peer-message fetchers — the CRM's read of the peers program (D2).

What must hold:

- the LEDGER is the only store: identity comes from foreign keys, and since
  ADR-186 the words live there too, so nothing hunts through a conversation
  archive for a text the relay had erased;
- the page for ONE person is narrowed in SQL, never sliced out of a global
  page — otherwise a total would face rows that contradict it;
- page and total come from ONE read, so a delivery landing mid-request cannot
  make them disagree;
- a message whose text expired keeps its date and reports no content;
- the flag gates the whole thing, and a database failure degrades the section
  to empty instead of taking the CRM page down with it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.domains.peers.schemas import PeerMessageActivity
from src.domains.relations.peer_messages import (
    fetch_peer_message_activity,
    fetch_peer_messages_for,
)
from src.domains.shared.aggregates import NameActivity

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
USER_ID = uuid4()
#: Folded key of the default fixture name — the CRM identity under test.
TARGET = "gerard dupont"


def _activity(
    *,
    direction: str = "received",
    name: str = "Gérard Dupont",
    minutes_ago: int = 10,
    text: str | None = "Gérard vous fait dire bonjour.",
) -> PeerMessageActivity:
    return PeerMessageActivity(
        message_id=uuid4(),
        peer_id=uuid4(),
        peer_display_name=name,
        direction=direction,
        occurred_at=NOW - timedelta(minutes=minutes_ago),
        text=text,
    )


def _patched(activity, *, enabled=True, db_error=False, aggregates=None):
    """Patch the ledger and the session, in one place."""
    import contextlib

    resolved = (
        list(aggregates)
        if aggregates is not None
        else [
            NameActivity(raw_name=item.peer_display_name, count=1, last_at=item.occurred_at)
            for item in activity
        ]
    )
    aggregate_mock = (
        AsyncMock(side_effect=SQLAlchemyError("ledger unavailable"))
        if db_error
        else AsyncMock(return_value=resolved)
    )
    repo = SimpleNamespace(
        aggregate_delivered_messages_by_peer=aggregate_mock,
        list_delivered_message_activity=AsyncMock(return_value=list(activity)),
    )

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace()

    return (
        patch("src.domains.relations.peer_messages.get_db_context", _ctx),
        patch("src.domains.relations.peer_messages.PeersRepository", return_value=repo),
        patch.object(
            __import__("src.domains.relations.peer_messages", fromlist=["settings"]).settings,
            "peers_enabled",
            enabled,
        ),
        repo,
    )


class TestFlagGate:
    async def test_disabled_flag_returns_nothing_without_touching_the_ledger(self) -> None:
        p_db, p_repo, p_flag, repo = _patched([_activity()], enabled=False)
        with p_db, p_repo, p_flag:
            page = await fetch_peer_messages_for(USER_ID, target_key=TARGET, limit=10)
        assert page.signals == [] and page.total == 0
        repo.aggregate_delivered_messages_by_peer.assert_not_awaited()

    async def test_a_blank_key_never_asks_anything(self) -> None:
        p_db, p_repo, p_flag, repo = _patched([_activity()])
        with p_db, p_repo, p_flag:
            page = await fetch_peer_messages_for(USER_ID, target_key="", limit=10)
        assert page.signals == [] and page.total == 0
        repo.aggregate_delivered_messages_by_peer.assert_not_awaited()


class TestContent:
    async def test_carries_the_text_the_ledger_kept(self) -> None:
        p_db, p_repo, p_flag, _ = _patched([_activity()])
        with p_db, p_repo, p_flag:
            (signal,) = (
                await fetch_peer_messages_for(USER_ID, target_key=TARGET, limit=10)
            ).signals
        assert signal.content == "Gérard vous fait dire bonjour."
        assert signal.direction == "received"
        assert signal.name_key == TARGET  # folded CRM identity key
        assert signal.peer_display_name == "Gérard Dupont"

    async def test_an_expired_text_keeps_its_date_and_reports_nothing(self) -> None:
        """Retention clears the words, never the fact (ADR-186) — and the same
        shape covers anything delivered before the ledger kept them at all."""
        item = _activity(text=None)
        p_db, p_repo, p_flag, _ = _patched([item])
        with p_db, p_repo, p_flag:
            (signal,) = (
                await fetch_peer_messages_for(USER_ID, target_key=TARGET, limit=10)
            ).signals
        assert signal.content is None
        assert signal.occurred_at == item.occurred_at

    async def test_a_sent_message_carries_the_senders_own_directive(self) -> None:
        p_db, p_repo, p_flag, _ = _patched(
            [_activity(direction="sent", text="Dis-lui que je serai en retard")]
        )
        with p_db, p_repo, p_flag:
            (signal,) = (
                await fetch_peer_messages_for(USER_ID, target_key=TARGET, limit=10)
            ).signals
        assert signal.direction == "sent"
        assert signal.content == "Dis-lui que je serai en retard"


class TestOnePersonAtATime:
    """The page is narrowed in SQL, never sliced out of a global page."""

    async def test_asks_the_ledger_for_this_persons_spellings_only(self) -> None:
        """Regression guard: slicing a global page would show a total with no
        rows behind it as soon as this person's messages fell outside the
        newest `limit` of the whole timeline."""
        p_db, p_repo, p_flag, repo = _patched(
            [],
            aggregates=[
                NameActivity(raw_name="Gérard Dupont", count=7, last_at=NOW),
                NameActivity(raw_name="gerard dupont", count=5, last_at=NOW),
                NameActivity(raw_name="Marie Leroy", count=99, last_at=NOW),
            ],
        )
        with p_db, p_repo, p_flag:
            page = await fetch_peer_messages_for(USER_ID, target_key=TARGET, limit=10)

        names = repo.list_delivered_message_activity.await_args.kwargs["peer_names"]
        assert sorted(names) == ["Gérard Dupont", "gerard dupont"]  # both, no one else
        # The total sums the person's spellings and ignores everyone else's.
        assert page.total == 12

    async def test_a_stranger_asks_the_ledger_for_nothing(self) -> None:
        p_db, p_repo, p_flag, repo = _patched([], aggregates=[])
        with p_db, p_repo, p_flag:
            page = await fetch_peer_messages_for(USER_ID, target_key="personne inconnue", limit=10)
        assert page.signals == [] and page.total == 0
        assert repo.list_delivered_message_activity.await_args.kwargs["peer_names"] == []


class TestFailureBoundary:
    async def test_database_failure_degrades_to_empty(self) -> None:
        """The peers bridge must never take the whole CRM page down."""
        p_db, p_repo, p_flag, _ = _patched([_activity()], db_error=True)
        with p_db, p_repo, p_flag:
            page = await fetch_peer_messages_for(USER_ID, target_key=TARGET, limit=10)
        assert page.signals == [] and page.total == 0

    async def test_the_overview_aggregate_degrades_too(self) -> None:
        p_db, p_repo, p_flag, _ = _patched([_activity()], db_error=True)
        with p_db, p_repo, p_flag:
            assert await fetch_peer_message_activity(USER_ID) == []


class TestOverviewAggregate:
    """The overview reads counts only — never the words."""

    async def test_returns_the_aggregate(self) -> None:
        p_db, p_repo, p_flag, repo = _patched([_activity(direction="received")])
        with p_db, p_repo, p_flag:
            rows = await fetch_peer_message_activity(USER_ID)
        assert [row.raw_name for row in rows] == ["Gérard Dupont"]
        # Counts only: the timeline (which carries the words) is never read.
        repo.list_delivered_message_activity.assert_not_awaited()

    async def test_disabled_flag_returns_empty(self) -> None:
        p_db, p_repo, p_flag, _ = _patched([_activity()], enabled=False)
        with p_db, p_repo, p_flag:
            assert await fetch_peer_message_activity(USER_ID) == []
