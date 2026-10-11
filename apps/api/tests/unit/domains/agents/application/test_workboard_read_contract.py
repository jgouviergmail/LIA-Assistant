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
