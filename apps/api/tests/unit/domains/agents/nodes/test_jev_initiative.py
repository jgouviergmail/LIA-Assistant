"""No initiative means no action, suggestion OR follow-up utility."""

import importlib
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "key,confidence,empty",
    [
        ("no_utility", 0.999, True),
        ("possible_utility", 0.999, False),
        ("unknown", 0.999, False),
        ("no_utility", 0.84, False),
    ],
)
async def test_only_high_confidence_absence_of_all_utility_can_skip(key, confidence, empty) -> None:
    module = importlib.import_module("src.domains.agents.nodes.jev_initiative")
    answer = ChoiceAnswer(
        type="choice", choice=key, confidence=confidence, probabilities={key: 0.999, "other": 0.001}
    )
    with patch.object(
        module,
        "choose_with_jev",
        AsyncMock(return_value=DecisionAttempt(outcome="success", answer=answer)),
    ) as native:
        result = await module.choose_empty_initiative(
            "Policy\nFacts\nMemory\nInterests\nAvailable tools", str(uuid4()), "run"
        )
    assert (result is not None) is empty
    if result is not None:
        assert (
            not result.should_act
            and not result.actions
            and result.suggestion is None
            and not result.followup_suggestions
        )
    assert native.call_args.kwargs["state"] == {
        "evaluation_context": "Policy\nFacts\nMemory\nInterests\nAvailable tools"
    }


@pytest.mark.parametrize("outcome", ["disabled", "timeout", "invalid_response", "missing_key"])
async def test_faults_preserve_full_evaluator(outcome) -> None:
    module = importlib.import_module("src.domains.agents.nodes.jev_initiative")
    with patch.object(
        module, "choose_with_jev", AsyncMock(return_value=DecisionAttempt(outcome=outcome))
    ):
        assert await module.choose_empty_initiative("Full context", str(uuid4()), "run") is None


@pytest.mark.parametrize("skip", [False, True])
async def test_node_preserves_suggestions_and_chips_when_native_defers(skip) -> None:
    from contextlib import ExitStack
    from unittest.mock import MagicMock

    from src.core.constants import STATE_KEY_INITIATIVE_FOLLOWUPS, STATE_KEY_INITIATIVE_SUGGESTION
    from src.domains.agents.nodes import initiative_node as node
    from src.domains.agents.nodes.initiative_schemas import InitiativeDecision

    empty = InitiativeDecision(analysis="Complete", should_act=False, reasoning="jev_no_utility")
    useful = InitiativeDecision(
        analysis="Scheduling problem",
        should_act=False,
        reasoning="Useful proposal",
        suggestion="Move the appointment?",
        followup_suggestions=["Check the return train"],
    )
    full = AsyncMock(return_value=useful)
    with ExitStack() as stack:
        stack.enter_context(patch.object(node.settings, "initiative_enabled", True))
        stack.enter_context(
            patch("src.domains.agents.services.response_context.start_response_context_prefetch")
        )
        for name, value in {
            "runtime_user_id_str": str(uuid4()),
            "_get_adjacent_read_only_manifests": [MagicMock()],
            "_format_execution_summary": "Complete results",
            "_format_tools_for_prompt": "Available tools",
            "_build_semantic_context": ("Dependencies", "Candidates"),
            "get_llm": MagicMock(),
        }.items():
            stack.enter_context(patch.object(node, name, return_value=value))
        stack.enter_context(patch.object(node, "_load_memory_facts", AsyncMock(return_value=[])))
        stack.enter_context(patch.object(node, "_load_user_interests", AsyncMock(return_value={})))
        gate = stack.enter_context(
            patch.object(
                node, "choose_empty_initiative", AsyncMock(return_value=empty if skip else None)
            )
        )
        stack.enter_context(patch.object(node, "get_structured_output", full))
        pushes = stack.enter_context(patch.object(node, "push_followups"))
        result = await node._initiative_core({"initiative_iteration": 0}, {})
    assert result["initiative_iteration"] == 1
    assert (
        "Complete results" in gate.call_args.args[0] and "Available tools" in gate.call_args.args[0]
    )
    if skip:
        full.assert_not_awaited()
        pushes.assert_not_called()
        assert (
            STATE_KEY_INITIATIVE_SUGGESTION not in result
            and STATE_KEY_INITIATIVE_FOLLOWUPS not in result
        )
    else:
        full.assert_awaited_once()
        assert result[STATE_KEY_INITIATIVE_SUGGESTION] == useful.suggestion
        assert result[STATE_KEY_INITIATIVE_FOLLOWUPS] == ["Check the return train"]
        pushes.assert_called_once()
