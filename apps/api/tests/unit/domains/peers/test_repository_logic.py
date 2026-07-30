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
class TestListAcceptedPeerNames:
    """CRM badge bridge (D2): folded, de-duplicated, blank-free peer names."""

    async def test_folds_dedupes_and_drops_blanks(self) -> None:
        repo = PeersRepository(db=AsyncMock())
        me = uuid4()
        other_a, other_b, other_c = uuid4(), uuid4(), uuid4()
        connections = [
            SimpleNamespace(user_a_id=me, user_b_id=other_a),
            SimpleNamespace(user_a_id=other_b, user_b_id=me),
            SimpleNamespace(user_a_id=me, user_b_id=other_c),
        ]
        repo.list_accepted_for_user = AsyncMock(return_value=connections)  # type: ignore[method-assign]
        rows = MagicMock()
        rows.all.return_value = [("Gérard Dupont",), ("gerard DUPONT",), (None,)]
        repo.db.execute = AsyncMock(return_value=rows)
        names = await repo.list_accepted_peer_names(me)
        assert names == ["gerard dupont"]

    async def test_no_connections_short_circuits(self) -> None:
        repo = PeersRepository(db=AsyncMock())
        repo.list_accepted_for_user = AsyncMock(return_value=[])  # type: ignore[method-assign]
        assert await repo.list_accepted_peer_names(uuid4()) == []
        repo.db.execute.assert_not_awaited()
