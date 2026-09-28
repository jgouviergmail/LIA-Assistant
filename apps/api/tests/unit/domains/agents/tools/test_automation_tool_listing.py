"""What the chat's listing tool tells the model about each routine (ADR-322).

A condition routine has no schedule: it used to crash the listing (its
``recurrence`` is NULL) and, before that, it announced its next CHECK as its
next run — « next automation in 6 minutes » for a watch that only runs when the
awaited fact happens. The listing states the system's clock instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.config import settings
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay, describe
from src.domains.agents.tools.automation_tools import _listed

pytestmark = pytest.mark.unit

NEXT = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
DAILY_AT_EIGHT = RecurrenceSpec(
    freq="daily",
    times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
    anchor_date=date(2026, 9, 1),
)


def _row(**over: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "title": "Routine",
        "trigger_kind": "time",
        "recurrence_spec": DAILY_AT_EIGHT,
        "condition_config": None,
        "user_timezone": "Europe/Paris",
        "is_enabled": True,
        "status": "active",
        "last_executed_at": None,
        "next_trigger_at": NEXT,
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_a_scheduled_routine_keeps_its_schedule_and_next_run() -> None:
    listed = _listed(_row(), "en")

    assert listed["schedule"] == describe(DAILY_AT_EIGHT, "en")
    assert listed["next_trigger_at"] == NEXT.isoformat()
    assert listed["trigger_kind"] == "time"


def test_a_watch_states_the_systems_clock_and_no_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
    watch = _row(
        trigger_kind="condition",
        recurrence_spec=None,
        condition_config={"type": "task_overdue"},
    )

    listed = _listed(watch, "en")

    assert listed["schedule"] == "Checked about every 10 min"
    assert listed["next_trigger_at"] is None
    assert listed["trigger_kind"] == "condition"
