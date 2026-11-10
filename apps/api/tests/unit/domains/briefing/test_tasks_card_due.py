"""The home's tasks card reads a task's day through the one door (2026-11-07, lot 6).

A task due today is on time, never overdue on its own day; a To Do due is its local midnight read
on the person's clock, which Graph answers as the evening before in UTC east of Greenwich; a Google
due is the date it names in every zone.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.formatters import format_task_item

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
NEW_YORK = ZoneInfo("America/New_York")


def test_a_to_do_task_due_today_in_paris_is_due_today() -> None:
    task = {
        "id": "t1",
        "title": "Pay",
        "status": "needsAction",
        "due": "2026-11-07T23:00:00.000Z",
        "_provider": "microsoft",
    }

    item = format_task_item(task, date(2026, 11, 8), zone=PARIS)

    assert item is not None
    assert (item.due_date_iso, item.days_until_due, item.overdue) == ("2026-11-08", 0, False)


def test_a_google_task_keeps_its_date_west_of_greenwich() -> None:
    task = {"id": "t1", "title": "Pay", "status": "needsAction", "due": "2026-11-08T00:00:00.000Z"}

    item = format_task_item(task, date(2026, 11, 8), zone=NEW_YORK)

    assert item is not None
    assert (item.due_date_iso, item.days_until_due, item.overdue) == ("2026-11-08", 0, False)


def test_a_day_passed_is_overdue_and_an_unreadable_one_leaves_the_task_undated() -> None:
    late = {"id": "t1", "title": "Pay", "status": "needsAction", "due": "2026-11-06T00:00:00.000Z"}
    odd = {"id": "t2", "title": "Call", "status": "needsAction", "due": "soon"}

    overdue = format_task_item(late, date(2026, 11, 8), zone=PARIS)
    undated = format_task_item(odd, date(2026, 11, 8), zone=PARIS)

    assert overdue is not None and overdue.overdue and overdue.days_until_due == -2
    assert undated is not None and undated.due_date_iso is None and not undated.overdue
