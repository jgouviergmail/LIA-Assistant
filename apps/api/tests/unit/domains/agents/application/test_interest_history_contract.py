"""Bounded history, complete UI fields and token-budget continuation are explicit contracts."""

import ast
import inspect
import json
import textwrap
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.interest_history_schemas import InterestHistoryRead
from src.domains.agents.tools.connector_cursor_projection import visible_connector_cursor
from src.domains.interests.management_history import read_interest_history_page
from src.domains.interests.schemas import InterestNotificationHistoryItem

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid",
    [
        {"limit": True},
        {"limit": "5"},
        {"limit": 0},
        {"limit": 51},
        {"actor_id": str(uuid4())},
        {"offset": 1},
    ],
)
def test_history_refuses_coercion_scope_and_mixed_paging(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InterestHistoryRead.model_validate(invalid)


def test_every_source_history_field_reaches_the_shared_projection() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(read_interest_history_page)))
    projection = next(
        node.args[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "InterestNotificationHistoryItem"
    )
    assert isinstance(projection, ast.Dict)
    assert {node.value for node in projection.keys if isinstance(node, ast.Constant)} == set(
        InterestNotificationHistoryItem.model_fields
    )


def test_budget_cut_does_not_skip_delivered_notifications() -> None:
    shown, fetched = str(uuid4()), str(uuid4())
    data = {
        "notifications": [{"id": shown, "content": "Delivered text"}],
        "total": 23,
        "returned_count": 5,
        "next_cursor": fetched,
        "truncated": False,
    }
    corrected = json.loads(
        visible_connector_cursor(
            json.dumps(data),
            {"application_interest_history_cursor": True},
            key="notifications",
            truncated=True,
        )
    )
    assert corrected["total"] == 23 and corrected["next_cursor"] == shown
    assert corrected["returned_count"] == 1 and corrected["truncated"]
