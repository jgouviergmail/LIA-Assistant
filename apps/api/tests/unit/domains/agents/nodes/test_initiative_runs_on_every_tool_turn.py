"""The initiative evaluator sees every eligible tool turn, whatever the turn brought back.

ADR-062: after an execution, one evaluation decides which read-only cross-domain checks
would enrich the answer (the weather on a route, the journey to an appointment, a
conflict with a proposed meeting) and, acting or not, proposes the suggestion, the
follow-up chips and their motivation. An e-mail-only gate (ADR-374, withdrawn on
2026-11-08) would have taken all of that away from every other turn.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import (
    STATE_KEY_INITIATIVE_FOLLOWUPS,
    STATE_KEY_INITIATIVE_SKIPPED_REASON,
)
from src.domains.agents.nodes import initiative_node as node
from src.domains.agents.nodes.initiative_schemas import InitiativeDecision

pytestmark = pytest.mark.unit

TURN = 3


def _item(item_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{item_type.lower()}_{uuid4().hex[:8]}",
        "type": item_type,
        "payload": payload,
        "meta": {"source": "synthetic", "domain": item_type.lower(), "turn_id": TURN},
    }


async def _invoke(registry: dict[str, Any]) -> tuple[dict[str, Any], AsyncMock]:
    decision = InitiativeDecision(
        analysis="Checked",
        should_act=False,
        reasoning="Nothing to add",
        followup_suggestions=["Show me the weather on arrival"],
    )
    evaluator = AsyncMock(return_value=decision)
    state = {
        "initiative_iteration": 0,
        "current_turn_id": TURN,
        "current_turn_registry": registry,
    }
    with ExitStack() as stack:
        stack.enter_context(patch.object(node.settings, "initiative_enabled", True))
        stack.enter_context(
            patch("src.domains.agents.services.response_context.start_response_context_prefetch")
        )
        stack.enter_context(patch.object(node, "runtime_user_id_str", return_value=str(uuid4())))
        stack.enter_context(
            patch.object(node, "_get_adjacent_read_only_manifests", return_value=[MagicMock()])
        )
        stack.enter_context(patch.object(node, "_format_tools_for_prompt", return_value="Tools"))
        stack.enter_context(
            patch.object(node, "_build_semantic_context", return_value=("Deps", "Candidates"))
        )
        stack.enter_context(patch.object(node, "_load_memory_facts", AsyncMock(return_value=[])))
        stack.enter_context(patch.object(node, "_load_user_interests", AsyncMock(return_value={})))
        stack.enter_context(patch.object(node, "get_llm", return_value=MagicMock()))
        stack.enter_context(patch.object(node, "get_structured_output", evaluator))
        result = await node.initiative_node(state, {})
    return result, evaluator


@pytest.mark.parametrize(
    "registry",
    [
        {},
        {
            "route": _item(
                "ROUTE",
                {"origin": "Synthetic Station", "destination": "12 Synthetic Street, Lyon"},
            )
        },
        {
            "event": _item(
                "EVENT",
                {"summary": "Synthetic review", "location": "12 Synthetic Street, Lyon"},
            )
        },
        {"email": _item("EMAIL", {"subject": "Synthetic", "snippet": "Synthetic body"})},
    ],
    ids=["no-item", "a-route", "an-appointment", "an-ordinary-email"],
)
async def test_every_eligible_tool_turn_reaches_the_evaluator(registry: dict[str, Any]) -> None:
    result, evaluator = await _invoke(registry)
    evaluator.assert_awaited_once()
    # Not acting, the evaluation still hands its follow-up chips to the answer.
    assert result.get(STATE_KEY_INITIATIVE_SKIPPED_REASON) == "Nothing to add"
    assert result[STATE_KEY_INITIATIVE_FOLLOWUPS] == ["Show me the weather on arrival"]
