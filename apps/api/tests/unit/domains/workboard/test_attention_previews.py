"""Grouped dashboard previews reuse the five real board reads and their predicates."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.sql import ClauseElement

from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository
from src.domains.workboard.summary_queries import read_attention

pytestmark = pytest.mark.unit
GROUPS = ("needs_me", "held_by_lia", "held_by_peers", "overdue", "open_total")


@pytest.mark.parametrize("limit", [1, 4])
async def test_each_preview_is_the_first_two_of_its_real_set_without_extra_reads(
    limit: int,
) -> None:
    me, peer, outsider = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)

    def due(days: int) -> str:
        return (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    tickets = [
        (1, me, None, "human", "waiting", due(1), "My question"),
        (2, me, None, "lia", "todo", due(-2), "Late LIA"),
        (3, me, peer, "human", "waiting", due(-1), "Late peer"),
        (4, me, peer, "lia", "in_progress", due(2), "Peer LIA first tie"),
        (5, me, None, "human", "todo", None, "Undated mine"),
        (6, outsider, peer, "human", "waiting", due(-9), "Invisible"),
        (7, me, peer, "human", "done", due(-9), "Closed"),
        (8, peer, me, "human", "waiting", None, "Inbound question"),
        (9, me, peer, "human", "todo", due(2), "Peer second tie"),
        (10, me, None, "lia", "todo", None, "Undated LIA"),
    ]
    statements: list[str] = []
    # `closing`: a sqlite3 connection's own `with` ends its TRANSACTION, never the
    # connection, which the garbage collector then closes with a ResourceWarning.
    with closing(sqlite3.connect(":memory:")) as connection:
        columns = ", ".join(f'"{column.name}"' for column in WorkboardTicket.__table__.columns)
        connection.execute(f"CREATE TABLE workboard_tickets ({columns})")
        connection.executemany(
            "INSERT INTO workboard_tickets "
            "(id, owner_user_id, assignee_user_id, assignee_kind, status, due_at, title) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    UUID(int=key).hex,
                    owner.hex,
                    holder.hex if holder else None,
                    kind,
                    status,
                    date,
                    title,
                )
                for key, owner, holder, kind, status, date, title in reversed(tickets)
            ],
        )

        async def execute(statement: ClauseElement) -> MagicMock:
            sql = str(
                statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            )
            # Compile the same statement for the production dialect too.
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            statements.append(sql)
            cursor = connection.execute(sql)
            rows = cursor.fetchall()
            names = [description[0] for description in cursor.description]
            result = MagicMock()
            result.all.return_value = rows
            if "preview_group" in names:
                assert set(names) == {"preview_group", "id", "title", "status", "due_at"}
                records = [dict(zip(names, row, strict=True)) for row in rows]
                result.all.return_value = [
                    (
                        record["preview_group"],
                        WorkboardTicket(
                            id=UUID(record["id"]),
                            title=record["title"],
                            status=record["status"],
                            due_at=(
                                datetime.fromisoformat(record["due_at"]).replace(tzinfo=UTC)
                                if record["due_at"]
                                else None
                            ),
                        ),
                    )
                    for record in records
                ]
            if rows:
                result.one.return_value = rows[0]
                result.scalar.return_value = rows[0][0]
            return result

        db = AsyncMock()
        db.execute.side_effect = execute
        figures = await read_attention(WorkboardRepository(db), me, now, limit=limit)

    assert (
        figures.needs_me,
        figures.held_by_lia,
        figures.held_by_peers,
        figures.overdue,
        figures.open_total,
    ) == (4, 3, 3, 2, 8)
    assert {
        key: [ticket.title for ticket in values] for key, values in figures.previews.items()
    } == {
        "needs_me": ["Late LIA", "Late peer"],
        "held_by_lia": ["Late LIA", "Peer LIA first tie"],
        "held_by_peers": ["Late peer", "Peer LIA first tie"],
        "overdue": ["Late LIA", "Late peer"],
        "open_total": ["Late LIA", "Late peer"],
    }
    assert [ticket.title for ticket in figures.needs_me_first] == [
        "Late LIA",
        "Late peer",
        "My question",
        "Inbound question",
    ][:limit]
    assert len(statements) == 5
    assert sum("UNION ALL" in sql for sql in statements) == 1


async def test_empty_board_has_five_known_empty_previews() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    result.one.return_value = (0, 0)
    result.scalar.return_value = 0
    db.execute.return_value = result
    figures = await read_attention(WorkboardRepository(db), uuid4(), datetime.now(UTC), limit=1)
    assert figures.previews == {key: [] for key in GROUPS}
    assert figures.needs_me_first == []
