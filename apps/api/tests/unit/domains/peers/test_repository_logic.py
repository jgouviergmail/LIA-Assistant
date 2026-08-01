"""Pure-logic tests for PeersRepository helpers (peers program, Lot 1, Task 5)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.peers.repository import PeersRepository, utc_day_bounds


@pytest.mark.unit
class TestUtcDayBounds:
    """Quota windows are UTC calendar days (spec §4.2)."""

    def test_covers_the_whole_utc_day(self):
        now = datetime(2026, 7, 29, 23, 59, 59, tzinfo=UTC)
        start, end = utc_day_bounds(now)
        assert start == datetime(2026, 7, 29, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)

    def test_midnight_belongs_to_the_new_day(self):
        now = datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)
        start, _end = utc_day_bounds(now)
        assert start == datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)

    def test_bounds_are_timezone_aware_utc(self):
        start, end = utc_day_bounds(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
        assert start.tzinfo is UTC
        assert end.tzinfo is UTC


@pytest.mark.unit
class TestListDeliveredMessageActivity:
    """CRM timeline rows: direction is relative to the CALLER, and a peer with
    no usable name never becomes a phantom '?' relationship card.

    The SQL itself (CASE counterpart join, block exclusion, delivered-only) is
    a PostgreSQL behavior and is covered in the integration tier — what the
    unit tier owns is the row → contract mapping.
    """

    ME = uuid4()

    @staticmethod
    def _repo_returning(rows: list[SimpleNamespace]) -> PeersRepository:
        """A repository whose single SELECT yields the given rows.

        ``db.execute`` is awaited but ``.all()`` is synchronous: an AsyncMock
        child would return a coroutine, so the result object is a MagicMock.
        """
        result = MagicMock()
        result.all.return_value = rows
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        return PeersRepository(db=db)

    def _row(self, *, sender_id, peer_id, full_name="Marie Leroy", when=None):
        return SimpleNamespace(
            message_id=uuid4(),
            peer_id=peer_id,
            sender_id=sender_id,
            full_name=full_name,
            delivered_at=when or datetime(2026, 7, 30, 9, 0, tzinfo=UTC),
            content="ma directive",
            delivered_text="ce que son assistant a dit",
        )

    async def test_direction_is_relative_to_the_caller(self) -> None:
        peer = uuid4()
        repo = self._repo_returning(
            [
                self._row(sender_id=self.ME, peer_id=peer),
                self._row(sender_id=peer, peer_id=peer),
            ]
        )
        activity = await repo.list_delivered_message_activity(self.ME, limit=10)
        assert [item.direction for item in activity] == ["sent", "received"]
        assert {item.peer_id for item in activity} == {peer}
        # Each side reads its OWN words — crossing them would undo the relay.
        assert [item.text for item in activity] == ["ma directive", "ce que son assistant a dit"]

    # The unattributable-peer exclusion USED to live here, as a Python
    # post-filter over the stubbed rows. It moved into the WHERE clause: run
    # after the LIMIT it emptied a page whose newest row happened to belong to
    # a nameless peer, while the aggregate — which excluded them in SQL — kept
    # reporting a total. Its oracle now lives where the SQL is real:
    # tests/integration/domains/peers/test_repository_db.py
    # ::test_a_nameless_peer_never_costs_a_real_row_its_place.

    async def test_maps_identity_and_instant_verbatim(self) -> None:
        peer = uuid4()
        when = datetime(2026, 7, 29, 18, 30, tzinfo=UTC)
        row = self._row(sender_id=peer, peer_id=peer, full_name="  Gérard Dupont  ", when=when)
        repo = self._repo_returning([row])
        (item,) = await repo.list_delivered_message_activity(self.ME, limit=10)
        assert item.message_id == row.message_id
        assert item.peer_display_name == "Gérard Dupont"  # trimmed, never folded
        assert item.occurred_at == when
