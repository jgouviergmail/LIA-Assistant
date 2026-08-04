"""The peers section of the notifications hub.

The hub lists, in one place, what LIA sent the reader and what is coming. Its
"relayed messages" section had no endpoint at all: the peers bridge could
answer "the newest N of the whole timeline" (no offset, no count) and "one
person's page" (for the CRM), neither of which is a pageable list with an exact
total.

Two properties matter more than the plumbing:

- the total is an AGGREGATE over the whole timeline, never the length of the
  page (ADR-185) — a hub that says "10 of 10" on an account with 200 exchanges
  is lying to the reader it exists to inform;
- the payload carries the caller's OWN side of each exchange, never the other
  person's words. Undoing the relay in a list view would be a leak the relay
  itself refuses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.peers.router import list_relayed_messages
from src.domains.peers.schemas import PeerMessageActivity

pytestmark = pytest.mark.unit


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _activity(index: int, *, text: str | None = "ce que j'ai dit") -> PeerMessageActivity:
    return PeerMessageActivity(
        message_id=uuid.uuid4(),
        peer_id=uuid.uuid4(),
        peer_display_name="Marie Client",
        direction="received" if index % 2 else "sent",
        occurred_at=datetime(2026, 8, 3, 10, index, tzinfo=UTC),
        text=text,
    )


async def _call(*, rows: list[PeerMessageActivity], total: int, limit: int = 10, offset: int = 0):
    user = _user()
    with patch("src.domains.peers.router.PeersRepository") as repo_cls:
        repo_cls.return_value.list_delivered_message_activity = AsyncMock(return_value=rows)
        repo_cls.return_value.count_delivered_messages = AsyncMock(return_value=total)
        page = await list_relayed_messages(limit=limit, offset=offset, user=user, db=AsyncMock())
        return page, repo_cls.return_value, user


class TestTheRelayedMessagesPage:
    async def test_the_total_is_the_whole_timeline_not_the_page(self) -> None:
        page, _, _ = await _call(rows=[_activity(i) for i in range(10)], total=214)

        assert len(page.messages) == 10
        assert page.total == 214

    async def test_the_page_window_reaches_the_repository(self) -> None:
        _, repo, user = await _call(rows=[], total=0, limit=25, offset=50)

        repo.list_delivered_message_activity.assert_awaited_once_with(user.id, limit=25, offset=50)

    async def test_the_count_is_scoped_to_the_caller(self) -> None:
        """A total is a claim ABOUT this account — never a global figure."""
        _, repo, user = await _call(rows=[], total=0)

        repo.count_delivered_messages.assert_awaited_once_with(user.id)

    async def test_it_carries_the_callers_own_side_of_the_exchange(self) -> None:
        page, _, _ = await _call(rows=[_activity(0, text="rappelle-lui le devis")], total=1)

        assert page.messages[0].content == "rappelle-lui le devis"
        assert page.messages[0].peer_display_name == "Marie Client"
        assert page.messages[0].direction == "sent"

    async def test_a_cleared_message_renders_as_absent_never_as_blank(self) -> None:
        """Retention (ADR-186) removes the text; the row itself still happened."""
        page, _, _ = await _call(rows=[_activity(0, text=None)], total=1)

        assert page.messages[0].content is None
        assert page.messages[0].occurred_at is not None

    async def test_an_empty_timeline_states_zero_rather_than_omitting_the_total(self) -> None:
        page, _, _ = await _call(rows=[], total=0)

        assert page.messages == []
        assert page.total == 0
