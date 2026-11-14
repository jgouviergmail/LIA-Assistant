"""Finite sections, source filter vocabularies, bounds and fields are reviewed contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.workboard_read_schemas import WorkboardUIQuery
from src.domains.workboard.constants import TicketPriority, TicketStatus
from src.domains.workboard.schemas import TicketRow

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"section": "ticket"},
        {"ticket_id": str(uuid4())},
        {"section": "comments", "ticket_id": str(uuid4()), "query": "irrelevant"},
        {"section": "admin"},
        {"limit": True},
        {"limit": 51},
        {"offset": -1},
        {"section": "board", "statuses": ["unknown"]},
        {"section": "board", "due_before": "2026-10-09T12:00:00"},
        {"owner_id": str(uuid4())},
        # The lane filter narrows the BOARD, like every other board filter.
        {"section": "needs_me", "categories": [str(uuid4())]},
        {"section": "summary", "uncategorized": True},
        {"section": "board", "categories": []},
        {"section": "board", "categories": ["Home"]},
        {"section": "board", "uncategorized": "yes"},
    ],
)
def test_workboard_query_refuses_ambiguous_or_foreign_scope(payload):
    with pytest.raises(ValidationError):
        WorkboardUIQuery.model_validate(payload)


def test_native_board_schema_reuses_source_enums_and_dtos():
    for status in TicketStatus:
        assert WorkboardUIQuery(section="board", statuses=(status,)).statuses == (status,)
    for priority in TicketPriority:
        assert WorkboardUIQuery(section="board", priorities=(priority,)).priorities == (priority,)
    assert {
        "run_claimed_at",
        "execution_mode",
        "total_cost_eur",
        "total_tokens_in",
        "follow_owner",
        "follow_assignee",
    } <= set(TicketRow.model_fields)


def test_the_board_read_takes_the_lane_filter_and_publishes_the_lanes():
    """What the screen can narrow to, the assistant's own read of that screen
    can — and it gets the lanes the screen draws, names included: a ticket row
    only holds an id."""
    from src.domains.agents.application.workboard_read_schemas import WorkboardUIProjection
    from src.domains.workboard.schemas import BoardPage

    category = uuid4()
    query = WorkboardUIQuery(section="board", categories=(category,), uncategorized=True)
    assert query.categories == (category,) and query.uncategorized is True
    assert WorkboardUIQuery(section="board").categories is None
    assert (
        WorkboardUIProjection.model_fields["lanes"].annotation
        == BoardPage.model_fields["lanes"].annotation
    )
