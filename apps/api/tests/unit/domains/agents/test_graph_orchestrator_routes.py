"""The orchestrator hands a pending confirmation to the HITL dispatch (graph.py).

ADR-367 removed the third pending kind (an entity disambiguation is now asked
before planning, by its own node): the two that remain must still reach the
person — a draft nobody is asked about would be executed unconfirmed.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.constants import NODE_DRAFT_CRITIQUE
from src.domains.agents.graph import route_from_orchestrator

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "pending",
    [
        {"pending_draft_critique": {"draft_id": "d1", "draft_type": "email_reply"}},
        {"pending_tool_confirmation": {"draft_id": "c1", "draft_type": "tool_call"}},
    ],
    ids=["draft", "tool_confirmation"],
)
def test_a_pending_confirmation_goes_to_the_hitl_dispatch(pending: dict[str, Any]) -> None:
    assert route_from_orchestrator(pending) == NODE_DRAFT_CRITIQUE


def test_nothing_pending_never_reaches_the_hitl_dispatch() -> None:
    state = {"pending_draft_critique": None, "pending_tool_confirmation": None}

    assert route_from_orchestrator(state) != NODE_DRAFT_CRITIQUE
