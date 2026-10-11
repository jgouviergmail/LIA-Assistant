"""The model's reminder count and cursor describe items actually delivered."""

import json
from uuid import uuid4

import pytest

from src.domains.agents.tools.connector_cursor_projection import visible_connector_cursor

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "key,flag",
    [("reminders", "application_reminder_cursor"), ("memories", "application_memory_cursor")],
)
def test_a_budget_cut_reports_the_shown_count_and_continues_after_that_item(
    key: str, flag: str
) -> None:
    shown = str(uuid4())
    projected = visible_connector_cursor(
        json.dumps(
            {
                key: [{"id": shown, "content": "Owned item"}],
                "returned_count": 5,
                "total_available": 5,
                "truncated": False,
                "next_cursor": None,
            }
        ),
        {flag: True},
        key=key,
        truncated=True,
    )
    data = json.loads(projected)
    assert data["returned_count"] == 1 and data["total_available"] == 5
    assert data["truncated"] is True and data["next_cursor"] == shown
