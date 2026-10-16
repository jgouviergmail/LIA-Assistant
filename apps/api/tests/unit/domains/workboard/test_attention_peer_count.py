"""The peer tile counts the board's real outbound open set, without new round trips."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import sqlite
from sqlalchemy.sql import ClauseElement

from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository
from src.domains.workboard.summary_queries import read_attention

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("copies", [1, 40])
async def test_exact_peer_count_uses_visible_open_outbound_set_in_one_holder_read(
    copies: int,
) -> None:
    me, peer, outsider = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    # Peer-held LIA overlaps the LIA total; late peer work overlaps needs-me.
    # Inbound work belongs to `me`, invisible and finished work never counts.
    tickets = [
        (me.hex, peer.hex, "human", "todo", None),
        (me.hex, peer.hex, "lia", "waiting", yesterday),
        (peer.hex, me.hex, "human", "todo", None),
        (peer.hex, me.hex, "lia", "in_progress", None),
        (outsider.hex, peer.hex, "human", "todo", None),
        (me.hex, peer.hex, "human", "done", None),
        (me.hex, None, "human", "todo", None),
        (me.hex, None, "lia", "todo", None),
        (me.hex, me.hex, "human", "waiting", None),
    ] * copies
    with sqlite3.connect(":memory:") as connection:
        # The count runs the actual SQLAlchemy statement. Unrelated PostgreSQL
        # column types/constraints are unnecessary for this read-only fixture.
        columns = ", ".join(f'"{column.name}"' for column in WorkboardTicket.__table__.columns)
        connection.execute(f"CREATE TABLE workboard_tickets ({columns})")
        connection.executemany(
            "INSERT INTO workboard_tickets "
            "(owner_user_id, assignee_user_id, assignee_kind, status, due_at) VALUES (?, ?, ?, ?, ?)",
            tickets,
        )
        statements: list[str] = []

        async def execute(statement: ClauseElement) -> MagicMock:
            sql = str(
                statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            )
            statements.append(sql)
            rows = connection.execute(sql).fetchall()
            row = rows[0] if rows else (0,)
            result = MagicMock()
            result.all.return_value = [] if "UNION ALL" in sql else rows
            result.one.return_value = row
            result.scalar.return_value = row[0]
            return result

        db = AsyncMock()
        db.execute.side_effect = execute
        repo = WorkboardRepository(db)
        repo.count_needs_me = AsyncMock(return_value=2 * copies)
        figures = await read_attention(repo, me, now, limit=2)

    assert figures.held_by_peers == 2 * copies
    assert figures.held_by_lia == 3 * copies
    assert figures.needs_me == 2 * copies
    assert figures.overdue == copies
    assert figures.open_total == 7 * copies
    assert figures.needs_me_first == []
    # Both holder aggregates share the original holder query; increasing the
    # number of tickets never adds SQL reads; the fourth read is the bounded preview.
    assert len(statements) == 4
    assert statements[1].count("count(*)") == 2
    assert " LIMIT " not in statements[1]


async def test_no_peer_ticket_returns_an_exact_zero() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.one.return_value = (0, 0)
    result.scalar.return_value = 0
    db.execute.return_value = result
    repo = WorkboardRepository(db)
    repo.counts_by_status = AsyncMock(return_value={})
    repo.count_needs_me = AsyncMock(return_value=0)

    figures = await read_attention(repo, uuid4(), datetime.now(UTC), limit=2)

    assert figures.held_by_peers == 0
    assert figures.open_total == 0
