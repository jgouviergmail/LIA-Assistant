"""Measuring what the two registers cost, so a purge is a decision (ADR-263).

The owner's arbitration, 2026-09-04: *keep everything for now, delete it all
with the account, and put a metric in Grafana so the day a purge is needed is a
measured day rather than a guessed one.*

That is the right way not to build something. The register grows at roughly
250 bytes a row (three UUIDs, a tool name, four short enumerations, a duration
and a timestamp, plus PostgreSQL's row header and two indexes) — about 9 MB a
year at a hundred calls a day, 45 MB at five hundred. Acceptable on a
self-hosted assistant, and unacceptable to assert without watching.

Two properties this file pins:

- **rows are an ESTIMATE and say so** (``pg_class.reltuples``, O(1)). A
  ``COUNT(*)`` every thirty seconds would be a sequential scan of the biggest
  table in the schema — the supervision would become the load it watches.
- **the size is the REAL one** (``pg_total_relation_size``, indexes included),
  because a disk fills with indexes as readily as with rows and the number an
  operator acts on is what the volume actually occupies.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.agents.effects.volume import (
    LEDGER_TABLES,
    TableVolume,
    ledger_volume,
)

pytestmark = [pytest.mark.unit]


class _Result:
    """A result that answers only what the code asks of it.

    Explicit rather than an ``AsyncMock``: a mock answers EVERY attribute with
    a coroutine, and the ones production never awaits are reported by the F028
    leak guard — a real rule, wrongly triggered by the double.
    """

    def __init__(self, rows: list[tuple[str, int, int]] | None = None, scalar: int = 0) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[tuple[str, int, int]]:
        return self._rows

    def scalar_one(self) -> int:
        return self._scalar


def _db(rows: list[tuple[str, int, int]], counted: int = 0) -> Any:
    """A session answering the volume query, and any exact count that follows."""

    class _Session:
        async def execute(self, statement: object, params: object = None) -> _Result:
            if "count" in str(statement).lower():
                return _Result(scalar=counted)
            return _Result(rows=rows)

    return _Session()


class TestBothRegistersAreWatched:
    def test_the_transparency_tables_are_the_watched_set(self) -> None:
        """The chain joined them in lot 5: notarising costs ~387 bytes per
        register row, which is a figure to watch rather than to estimate."""
        assert set(LEDGER_TABLES) == {"agent_effects", "agent_treatments", "ledger_chain"}

    async def test_it_reports_one_volume_per_table(self) -> None:
        volumes = await ledger_volume(
            _db(
                [
                    ("agent_effects", 1200, 409_600),
                    ("agent_treatments", 8400, 1_048_576),
                    ("ledger_chain", 9600, 655_360),
                ]
            )
        )

        assert volumes == [
            TableVolume(table="agent_effects", rows=1200, size_bytes=409_600),
            TableVolume(table="agent_treatments", rows=8400, size_bytes=1_048_576),
            TableVolume(table="ledger_chain", rows=9600, size_bytes=655_360),
        ]

    async def test_a_table_the_query_did_not_see_reports_zero(self) -> None:
        """A fresh install has no statistics yet; that is zero, not silence.

        A gauge that stops being published reads as "no data" on a panel, which
        an operator cannot distinguish from a broken exporter.
        """
        volumes = await ledger_volume(_db([("agent_effects", 10, 8192)]))

        assert TableVolume(table="agent_treatments", rows=0, size_bytes=0) in volumes


class TestTheFigureIsNeverAContradiction:
    """A gauge that says "0 rows, 73 KB" is a gauge nobody can act on.

    Measured on the dev instance 2026-09-04: five consultation rows existed,
    ``lia_ledger_bytes`` moved from 32 768 to 73 728, and ``lia_ledger_rows``
    read 0 — because ``pg_class.reltuples`` is -1 until the first ANALYZE and
    autovacuum had not run yet. An estimate is acceptable; an estimate that
    reads ZERO on a table holding rows is a false statement, and this codebase
    does not ship counts that are wrong (ADR-185).

    The rule: a NON-POSITIVE estimate is not an estimate, so the row is counted
    exactly. That is self-balancing — a table big enough for ``COUNT(*)`` to
    matter has long since been analysed and reports a positive estimate.
    """

    async def test_a_never_analysed_table_is_counted_exactly(self) -> None:
        counted: list[str] = []

        async def _execute(statement: object, params: object = None) -> object:
            text = str(statement)
            if "count" in text.lower():
                counted.append(text)
                result = AsyncMock()
                result.scalar_one = lambda: 5
                return result
            result = AsyncMock()
            result.all = lambda: [("agent_treatments", -1, 73728)]
            return result

        session = AsyncMock()
        session.execute = _execute

        volumes = await ledger_volume(session)

        assert counted, "a table with no usable estimate was not counted"
        treatments = next(v for v in volumes if v.table == "agent_treatments")
        assert treatments.rows == 5, "the gauge kept reporting zero rows for 73 KB"
        assert treatments.size_bytes == 73728

    async def test_a_positive_estimate_is_trusted_and_costs_no_count(self) -> None:
        """The cheap path stays cheap: no scan once the table is analysed."""
        counted: list[str] = []

        async def _execute(statement: object, params: object = None) -> object:
            text = str(statement)
            if "count" in text.lower():
                counted.append(text)
            result = AsyncMock()
            result.all = lambda: [
                ("agent_effects", 1200, 409600),
                ("agent_treatments", 84000, 10485760),
                ("ledger_chain", 96000, 12582912),
            ]
            result.scalar_one = lambda: 0
            return result

        session = AsyncMock()
        session.execute = _execute

        volumes = await ledger_volume(session)

        assert counted == [], "an analysed table was scanned for nothing"
        assert [v.rows for v in volumes] == [1200, 84000, 96000]

    async def test_a_failing_count_degrades_to_zero_rather_than_losing_the_size(
        self,
    ) -> None:
        """The size is the figure an operator acts on; it must survive."""

        async def _execute(statement: object, params: object = None) -> object:
            text = str(statement)
            if "count" in text.lower():
                raise RuntimeError("permission denied")
            result = AsyncMock()
            result.all = lambda: [("agent_effects", 0, 8192)]
            return result

        session = AsyncMock()
        session.execute = _execute

        volumes = await ledger_volume(session)

        effects = next(v for v in volumes if v.table == "agent_effects")
        assert effects.rows == 0
        assert effects.size_bytes == 8192


class TestWatchingNeverBreaksTheLoop:
    async def test_a_failing_query_reports_nothing_rather_than_raising(self) -> None:
        """The periodic loop syncs many metrics; one must not take the rest down."""
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("no pg_class here"))

        assert await ledger_volume(session) == []
