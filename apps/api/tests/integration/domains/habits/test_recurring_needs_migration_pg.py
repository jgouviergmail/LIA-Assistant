"""The ADR-375 data transition, run on a real PostgreSQL (review focus 5).

The revision's own ``downgrade`` then ``upgrade`` run through an Alembic
``Operations`` context bound to the test's connection: the schema starts at
head (built from the models), so the downgrade brings the mute column back,
v1 rows are written the way the old code wrote them, and the upgrade must
delete what is derived, convert what the person decided, and leave no row a
v2 reader would refuse.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.discussion_projection import RecurringPayload
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_11_08_1920-5f4ae86b5823_recurring_needs_v2.py"
)
SEEN = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("recurring_needs_v2", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


async def _v1(
    session: AsyncSession, user_id: UUID, key: str, status: str, payload: dict[str, Any]
) -> None:
    await session.execute(
        text(
            "INSERT INTO user_habits (id, created_at, updated_at, user_id, kind, key, payload, "
            "positive_signals, negative_signals, status, last_observed_at, muted_until_reproof) "
            "VALUES (:id, now(), now(), :u, 'recurring_request', :k, CAST(:p AS jsonb), 0, 0, :s, "
            ":seen, true)"
        ),
        {
            "id": uuid4(),
            "u": user_id,
            "k": key,
            "p": json.dumps(payload),
            "s": status,
            "seen": SEEN,
        },
    )


async def test_active_v1_needs_are_relearned_and_decided_ones_converted(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"needs-{uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    await _migrate(db_session, MIGRATION.downgrade)
    await _v1(
        db_session,
        user.id,
        "email",
        "active",
        {
            "version": 1,
            "shape": "daily",
            "trigger_hour": 8.5,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            "distinct_days": 9,
            "occurrences": 11,
            "offer_dates": ["2026-10-30"],
        },
    )
    await _v1(
        db_session,
        user.id,
        "event",
        "paused",
        {
            "version": 1,
            "shape": "weekly",
            "trigger_hour": 19.5,
            "days_of_week": [6],
            "distinct_days": 4,
            "occurrences": 4,
            "usual_intent": "search",
        },
    )
    await _v1(
        db_session,
        user.id,
        "task",
        "blocked",
        {
            "version": 1,
            "shape": "intermittent",
            "trigger_hour": None,
            "days_of_week": [],
            "distinct_days": 6,
            "occurrences": 6,
        },
    )

    await _migrate(db_session, MIGRATION.upgrade)

    rows = {
        key: (status, payload)
        for key, status, payload in (
            await db_session.execute(
                text("SELECT key, status, payload FROM user_habits WHERE user_id = :u"),
                {"u": user.id},
            )
        ).all()
    }
    assert set(rows) == {"event", "task"}  # the ACTIVE row is relearned, not converted
    status, event = rows["event"]
    assert status == "paused"
    assert (event["version"], event["cadence"], event["weekday"]) == (2, "weekly", 6)
    assert (event["usual_hour"], event["part_of_day"], event["usual_intent"]) == (
        19.5,
        "evening",
        "search",
    )
    assert "offer_dates" not in event and "trigger_hour" not in event
    status, task = rows["task"]
    assert status == "blocked"
    assert (task["cadence"], task["part_of_day"], task["usual_hour"]) == ("daily", "any", 12.0)
    for _status, payload in rows.values():
        RecurringPayload.model_validate(payload)  # every v2 reader accepts what is left

    columns = (
        await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'user_habits' AND column_name = 'muted_until_reproof'"
            )
        )
    ).all()
    assert columns == []
