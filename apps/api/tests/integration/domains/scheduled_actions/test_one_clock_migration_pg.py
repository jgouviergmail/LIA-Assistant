"""The ADR-322 migration, run on a real PostgreSQL, both ways and back.

The revision's own ``upgrade`` and ``downgrade`` are executed through an
Alembic ``Operations`` context bound to the test's connection — the DDL, the
row rewrites and the constraint are the ones production will run, inside the
test's rolled-back transaction.

What must hold:

- a condition routine loses its schedule and keeps its END (a date, the day of
  its last instant, or none), a finished one is left for the sweep to close, a
  running one is checked within ten minutes rather than at its old hour;
- a paused routine keeps its trigger: nothing brings forward what nobody runs;
- the two rows no writer produces are repaired rather than failing the CHECK;
- the CHECK then refuses a routine with two clocks, or none;
- the downgrade gives a schedule back ending on the watched day, and a second
  upgrade lands on the same rows.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_09_25_2000-3e625df0094a_routine_one_clock.py"
)
PARIS = ZoneInfo("Europe/Paris")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("routine_one_clock", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    """Run one direction of the revision on the test's own connection."""

    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


def _spec(anchor: date, end: dict[str, object]) -> dict[str, object]:
    return {
        "freq": "daily",
        "interval": 1,
        "anchor_date": anchor.isoformat(),
        "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}, {"hour": 17, "minute": 0}]},
        "end": end,
    }


async def _insert(
    session: AsyncSession,
    user_id: UUID,
    *,
    kind: str,
    recurrence: dict[str, object] | None,
    condition: dict[str, object] | str | None,
    next_trigger_at: datetime | None,
    is_enabled: bool = True,
) -> UUID:
    """A row in the PRE-upgrade shape, written in SQL: the model forbids it now."""
    action_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO scheduled_actions (id, user_id, title, action_prompt, recurrence, "
            "user_timezone, next_trigger_at, trigger_kind, condition_config, requires_approval, "
            "execution_mode, is_enabled, status, execution_count, consecutive_failures, "
            "created_at, updated_at) VALUES (:id, :user_id, 'r', 'p', CAST(:recurrence AS JSONB), "
            "'Europe/Paris', :next_at, :kind, CAST(:condition AS JSONB), false, 'react', "
            ":enabled, 'active', 0, 0, now(), now())"
        ),
        {
            "id": action_id,
            "user_id": user_id,
            "recurrence": None if recurrence is None else _json(recurrence),
            "next_at": next_trigger_at,
            "kind": kind,
            # A str is sent verbatim: ``"null"`` is the JSON null the service
            # wrote for every time routine before ``none_as_null``.
            "condition": (
                None
                if condition is None
                else condition if isinstance(condition, str) else _json(condition)
            ),
            "enabled": is_enabled,
        },
    )
    return action_id


def _json(value: dict[str, object]) -> str:
    import json

    return json.dumps(value)


async def _row(session: AsyncSession, action_id: UUID) -> Any:
    return (
        await session.execute(
            text(
                "SELECT trigger_kind, recurrence, condition_config, next_trigger_at, "
                "is_enabled, status FROM scheduled_actions WHERE id = :id"
            ),
            {"id": action_id},
        )
    ).one()


@pytest.mark.asyncio
async def test_the_migration_both_ways_and_back(async_session: AsyncSession) -> None:
    session = async_session
    user = User(email=f"one_clock_{uuid4().hex}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()

    # The table as it was: no constraint, a schedule on every routine.
    await _migrate(session, MIGRATION.downgrade)

    now = datetime.now(UTC)
    today = now.astimezone(PARIS).date()
    tomorrow_nine = datetime.combine(
        today + timedelta(days=1), datetime.min.time(), PARIS
    ) + timedelta(hours=9)
    dated = await _insert(
        session,
        user.id,
        kind="condition",
        recurrence=_spec(
            today, {"kind": "on_date", "on_date": (today + timedelta(days=7)).isoformat()}
        ),
        condition={"type": "mail_match", "query": "devis"},
        next_trigger_at=tomorrow_nine,
    )
    exhausted = await _insert(
        session,
        user.id,
        kind="condition",
        # Four checks from four days ago: the series ended three days ago.
        recurrence=_spec(today - timedelta(days=4), {"kind": "after_count", "after_count": 4}),
        condition={"type": "task_overdue"},
        next_trigger_at=None,
    )
    endless = await _insert(
        session,
        user.id,
        kind="condition",
        recurrence=_spec(today, {"kind": "never"}),
        condition={"type": "document_added"},
        next_trigger_at=tomorrow_nine,
    )
    paused = await _insert(
        session,
        user.id,
        kind="condition",
        recurrence=_spec(today, {"kind": "never"}),
        condition={"type": "task_overdue"},
        next_trigger_at=tomorrow_nine,
        is_enabled=False,
    )
    timed = await _insert(
        session,
        user.id,
        kind="time",
        recurrence=_spec(today, {"kind": "never"}),
        condition={"type": "task_overdue"},  # stray: no writer produces this
        next_trigger_at=tomorrow_nine,
    )
    orphan = await _insert(
        session,
        user.id,
        kind="condition",
        recurrence=_spec(today, {"kind": "never"}),
        condition=None,  # no writer produces this either
        next_trigger_at=tomorrow_nine,
    )
    # What the service REALLY wrote for a time routine: the JSON null, which
    # `IS NULL` does not match — the CHECK would refuse it untouched.
    json_null_time = await _insert(
        session,
        user.id,
        kind="time",
        recurrence=_spec(today, {"kind": "never"}),
        condition="null",
        next_trigger_at=tomorrow_nine,
    )
    json_null_condition = await _insert(
        session,
        user.id,
        kind="condition",
        recurrence=_spec(today, {"kind": "never"}),
        condition="null",
        next_trigger_at=tomorrow_nine,
    )

    await _migrate(session, MIGRATION.upgrade)
    first_pass = {
        action_id: await _row(session, action_id)
        for action_id in (
            dated,
            exhausted,
            endless,
            paused,
            timed,
            orphan,
            json_null_time,
            json_null_condition,
        )
    }

    row = first_pass[dated]
    assert row.recurrence is None
    assert row.condition_config == {
        "type": "mail_match",
        "query": "devis",
        "until": (today + timedelta(days=7)).isoformat(),
    }
    window = timedelta(minutes=MIGRATION.BRING_FORWARD_MINUTES)
    assert row.next_trigger_at <= datetime.now(UTC) + window

    row = first_pass[exhausted]
    assert row.recurrence is None
    assert row.condition_config["until"] == (today - timedelta(days=3)).isoformat()
    assert row.next_trigger_at is None  # the sweep closes it

    row = first_pass[endless]
    assert "until" not in row.condition_config
    assert row.next_trigger_at <= datetime.now(UTC) + window

    # Nobody runs a paused routine: nothing is brought forward.
    assert first_pass[paused].next_trigger_at == tomorrow_nine

    row = first_pass[timed]
    assert row.recurrence is not None
    assert row.condition_config is None

    row = first_pass[orphan]
    assert row.trigger_kind == "time"
    assert row.is_enabled is False
    assert row.status == "error"

    # The JSON null reads as no condition, on both kinds.
    assert first_pass[json_null_time].condition_config is None
    row = first_pass[json_null_condition]
    assert (row.trigger_kind, row.status) == ("time", "error")

    # The table now refuses two clocks, and none.
    for kind, recurrence, condition in (
        ("condition", _spec(today, {"kind": "never"}), {"type": "task_overdue"}),
        ("time", None, None),
    ):
        # The error leaves the savepoint so the savepoint is rolled back.
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await _insert(
                    session,
                    user.id,
                    kind=kind,
                    recurrence=recurrence,
                    condition=condition,
                    next_trigger_at=None,
                )

    # Back: a schedule again, ending on the watched day.
    await _migrate(session, MIGRATION.downgrade)
    row = await _row(session, dated)
    assert row.recurrence["end"] == {
        "kind": "on_date",
        "on_date": (today + timedelta(days=7)).isoformat(),
        "after_count": None,
    }
    assert "until" not in row.condition_config
    assert [(t["hour"], t["minute"]) for t in row.recurrence["times"]["at"]] == [(9, 0), (17, 0)]

    # And forth again: the same rows.
    await _migrate(session, MIGRATION.upgrade)
    for action_id in (dated, exhausted, endless):
        again = await _row(session, action_id)
        assert again.recurrence is None
        assert again.condition_config == first_pass[action_id].condition_config

    # The model reads every migrated row.
    migrated = (
        (await session.execute(select(ScheduledAction).where(ScheduledAction.user_id == user.id)))
        .scalars()
        .all()
    )
    assert {
        action.recurrence_spec is None for action in migrated if action.trigger_kind == "condition"
    } == {True}
