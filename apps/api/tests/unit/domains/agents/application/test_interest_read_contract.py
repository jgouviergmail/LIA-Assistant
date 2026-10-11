"""Strict management selection and token-budget paging preserve source contracts."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.interest_read_schemas import InterestRead
from src.domains.agents.tools.connector_cursor_projection import visible_connector_cursor

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid",
    [
        {"limit": True},
        {"limit": "5"},
        {"limit": 0},
        {"limit": 51},
        {"actor_id": str(uuid4())},
        {"status": "invalid"},
        {"category": "invalid"},
        {"interest_id": str(uuid4()), "status": "active"},
        {"interest_id": str(uuid4()), "after_id": str(uuid4())},
    ],
)
def test_read_refuses_ambiguous_and_coerced_selection(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InterestRead.model_validate(invalid)


def test_model_budget_cut_continues_after_the_last_actually_shown_interest() -> None:
    visible, fetched_last = str(uuid4()), str(uuid4())
    data = {
        "interests": [{"id": visible, "topic": "Visible topic"}],
        "next_cursor": fetched_last,
        "returned_count": 5,
        "truncated": False,
        "total": 105,
        "total_available": 50,
    }
    corrected = json.loads(
        visible_connector_cursor(
            json.dumps(data), {"application_interest_cursor": True}, key="interests", truncated=True
        )
    )
    assert (
        corrected["next_cursor"] == visible
        and corrected["returned_count"] == 1
        and corrected["truncated"]
    )
    assert corrected["total"] == 105 and corrected["total_available"] == 50
