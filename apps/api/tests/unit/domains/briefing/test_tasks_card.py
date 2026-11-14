"""The tasks card's assembly: what every list gave, as the card shows it (2026-11-10).

Each task names its own list, by its real id and its name, as the walk stamped it; one order
runs across the lists; what is done never stands on the card.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.core.field_names import FIELD_TASK_LIST_ID, FIELD_TASK_LIST_NAME
from src.domains.briefing.tasks_card import card_items

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
TODAY = date(2026, 11, 10)


def _task(title: str, offset: int | None, list_id: str = "l-home", **extra: Any) -> dict[str, Any]:
    due = (
        None if offset is None else f"{(TODAY + timedelta(days=offset)).isoformat()}T00:00:00.000Z"
    )
    return {
        "id": title,
        "title": title,
        "status": "needsAction",
        "due": due,
        FIELD_TASK_LIST_ID: list_id,
        FIELD_TASK_LIST_NAME: list_id.removeprefix("l-").title(),
        **extra,
    }


class TestCardItems:
    def test_one_order_runs_across_the_lists_each_task_naming_its_own(self) -> None:
        tasks = [
            _task("tomorrow", 1),
            _task("undated", None),
            _task("late", -3, "l-work"),
            _task("today", 0, "l-work"),
        ]

        items = card_items(tasks, today=TODAY, zone=PARIS)

        assert [(item.title, item.list_id, item.list_name) for item in items] == [
            ("late", "l-work", "Work"),
            ("today", "l-work", "Work"),
            ("tomorrow", "l-home", "Home"),
            ("undated", "l-home", "Home"),
        ]

    def test_what_is_done_never_stands_on_the_card(self) -> None:
        tasks = [_task("done", -1, status="completed"), _task("open", 0)]

        items = card_items(tasks, today=TODAY, zone=PARIS)

        assert [item.title for item in items] == ["open"]

    def test_a_task_whose_list_has_no_name_names_none(self) -> None:
        [item] = card_items(
            [{**_task("open", 0), FIELD_TASK_LIST_NAME: None}], today=TODAY, zone=PARIS
        )

        assert (item.list_id, item.list_name) == ("l-home", None)

    def test_no_task_is_an_empty_card(self) -> None:
        assert card_items([], today=TODAY, zone=PARIS) == []
