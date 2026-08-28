"""Diagnostics persistence — model contracts and the atomic incident upsert.

What a unit test CAN prove without PostgreSQL: the table metadata (partial
unique index guaranteeing at most ONE open incident per correlation key), the
timezone-awareness of every datetime column, and the SHAPE of the upsert
statement (ON CONFLICT targeting that partial index — the ChatRepository
atomic-upsert doctrine, never SELECT→increment). Two-actor behaviour runs in
the integration suite against a real database.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import DateTime
from sqlalchemy.dialects import postgresql

from src.domains.diagnostics.models import (
    INCIDENT_OPEN_PARTIAL_INDEX_NAME,
    HealthSnapshot,
    Incident,
)
from src.domains.diagnostics.repository import build_open_or_touch_stmt


@pytest.mark.unit
class TestHealthSnapshotModel:
    def test_table_and_columns(self) -> None:
        table = HealthSnapshot.__table__
        assert table.name == "health_snapshots"
        assert isinstance(table.c.taken_at.type, DateTime)
        assert table.c.taken_at.type.timezone is True
        assert table.c.overall.nullable is False
        assert table.c.results.nullable is False


@pytest.mark.unit
class TestIncidentModel:
    def test_table_and_columns(self) -> None:
        table = Incident.__table__
        assert table.name == "incidents"
        assert table.c.correlation_key.nullable is False
        assert table.c.status.nullable is False
        for column in ("opened_at", "last_seen_at", "resolved_at", "notified_at"):
            assert table.c[column].type.timezone is True, column

    def test_partial_unique_index_guards_single_open_incident(self) -> None:
        index = next(
            idx
            for idx in Incident.__table__.indexes
            if idx.name == INCIDENT_OPEN_PARTIAL_INDEX_NAME
        )
        assert index.unique is True
        assert [c.name for c in index.columns] == ["correlation_key"]
        where = index.dialect_options["postgresql"]["where"]
        assert "open" in str(where)


@pytest.mark.unit
class TestOpenOrTouchStatement:
    def test_upsert_targets_the_partial_index(self) -> None:
        stmt = build_open_or_touch_stmt(
            correlation_key="RedisDown",
            source="alert",
            severity="critical",
            title="Redis is down",
            alertname="RedisDown",
            fingerprint="abc123",
            evidence={"summary": "redis-exporter unreachable"},
            now=datetime.now(UTC),
        )
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT (correlation_key) WHERE" in sql
        assert "DO UPDATE" in sql
        # The touch path refreshes recency, never re-opens or rewrites history.
        assert "last_seen_at" in sql

    def test_upsert_carries_returning_for_created_detection(self) -> None:
        stmt = build_open_or_touch_stmt(
            correlation_key="k",
            source="self_check",
            severity="critical",
            title="t",
            alertname=None,
            fingerprint=None,
            evidence={},
            now=datetime.now(UTC),
        )
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "RETURNING" in sql
