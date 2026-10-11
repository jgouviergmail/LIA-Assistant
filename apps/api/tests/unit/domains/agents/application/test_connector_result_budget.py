"""A model cursor must continue after the last visible item when its budget cuts a page."""

import json
from uuid import uuid4

import pytest

from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("last_page", [False, True])
def test_budgeted_page_does_not_skip_received_but_omitted_connector_rows(last_page: bool) -> None:
    identities = [str(uuid4()) for _ in range(3)]
    source = {
        "connectors": [
            {"id": identity, "preferences": {"default_calendar_name": "calendar " * 100}}
            for identity in identities
        ],
        "total": 3,
        "next_cursor": None if last_page else identities[-1],
    }
    output = UnifiedToolOutput.data_success(
        message="Saved preferences",
        structured_data=source,
        metadata={"application_connector_cursor": True},
    )
    projected = json.loads(extract_data_for_llm(output, budget_tokens=100))
    assert len(projected["connectors"]) == 1
    assert projected["next_cursor"] == identities[0]
    assert source["next_cursor"] == (None if last_page else identities[-1])
    assert len(source["connectors"]) == 3


def test_shared_server_budget_cut_keeps_every_preference_reachable() -> None:
    source = {
        "servers": [
            {"server_key": key, "name": key * 100, "enabled_for_user": True}
            for key in ("first", "second", "third")
        ],
        "total": 3,
        "next_cursor": None,
    }
    output = UnifiedToolOutput.data_success(
        message="Personal shared preferences",
        structured_data=source,
        metadata={"application_shared_mcp_cursor": True},
    )
    projected = json.loads(extract_data_for_llm(output, budget_tokens=100))
    assert len(projected["servers"]) == 1
    assert projected["next_cursor"] == "first"
    assert source["next_cursor"] is None and len(source["servers"]) == 3
