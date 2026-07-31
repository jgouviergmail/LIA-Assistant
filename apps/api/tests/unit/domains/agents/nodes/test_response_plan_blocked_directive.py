"""The blocked-plan directive must reach the response prompt, and only then.

``_build_response_chain`` assembles the system blocks of the answer. Three
directives can occupy the same slot and they are not interchangeable:

- plan rejection — the USER refused the plan;
- draft cancellation — the USER cancelled an action;
- plan blocked (this one) — the SYSTEM refused steps the user never saw.

The first two describe a decision the user made and already knows about. The
third describes a failure they are entitled to hear, and which the model would
otherwise invent an explanation for (2026-07-30: three consecutive turns
blaming the user's configuration for a routing bug). Priority between them is
therefore behaviour, not a detail — it is asserted here in both directions.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.nodes.response_node import _build_response_chain
from src.domains.agents.orchestration.validator import ValidationIssue, ValidationResult
from src.domains.agents.tools.common import ToolErrorCode

BLOCKED_MARKER = "PLAN BLOCKED BY VALIDATION"
REJECTION_MARKER = "PLAN REJECTION"
CANCELLED_MARKER = "DRAFT"


def _invalid_plan() -> ValidationResult:
    """The verbatim validator verdict of request 303d7ce3."""
    return ValidationResult(
        is_valid=False,
        errors=[
            ValidationIssue(
                severity="error",
                code=ToolErrorCode.UNAUTHORIZED,
                message="Missing required scopes: https://www.googleapis.com/auth/calendar",
                step_index=0,
                tool_name="get_events_tool",
            )
        ],
        total_steps=1,
    )


def _system_blocks(state: dict, plan_rejection_reason: str | None = None) -> str:
    """Build the chain and return every system block, concatenated."""
    captured: dict[str, list] = {}

    class _Template:
        @staticmethod
        def from_messages(messages):
            captured["messages"] = messages
            template = MagicMock()
            template.__or__ = lambda self, other: "chain"
            return template

    with patch("src.domains.agents.nodes.response_node.ChatPromptTemplate", _Template):
        _build_response_chain(
            base_system_prompt="BASE",
            agent_results_summary="",
            skills_context="",
            plan_rejection_reason=plan_rejection_reason,
            state=state,
            user_language="fr",
            llm=MagicMock(),
        )

    # The list is heterogeneous: ("role", text) tuples plus a
    # MessagesPlaceholder — only the system tuples carry directives.
    return "\n".join(
        str(entry[1])
        for entry in captured["messages"]
        if isinstance(entry, tuple) and len(entry) == 2 and entry[0] == "system"
    )


def test_blocked_plan_injects_the_directive():
    blocks = _system_blocks({"validation_result": _invalid_plan()})

    assert BLOCKED_MARKER in blocks


def test_directive_names_the_blocked_tool_and_its_cause():
    """The whole point: the model is told WHAT failed, not left guessing."""
    blocks = _system_blocks({"validation_result": _invalid_plan()})

    assert "get_events_tool" in blocks
    assert "not connected or authorized" in blocks


def test_directive_carries_the_user_language():
    assert "fr" in _system_blocks({"validation_result": _invalid_plan()})


def test_directive_forbids_generalizing_beyond_the_blocked_list():
    """The exact sentence the assistant produced must be ruled out."""
    blocks = _system_blocks({"validation_result": _invalid_plan()})

    assert "NEVER generalize" in blocks
    assert "nothing is configured" in blocks


def test_directive_never_leaks_raw_scope_urls():
    assert "https://www.googleapis.com" not in _system_blocks(
        {"validation_result": _invalid_plan()}
    )


def test_valid_plan_injects_nothing():
    """The common path must be byte-identical to before this change."""
    blocks = _system_blocks({"validation_result": ValidationResult(is_valid=True)})

    assert BLOCKED_MARKER not in blocks


def test_absent_validation_result_injects_nothing():
    """Conversation and ReAct turns never run the validator."""
    assert BLOCKED_MARKER not in _system_blocks({})


def test_user_rejection_wins_over_the_blocked_directive():
    """A plan the USER refused is not a system failure — do not report one."""
    blocks = _system_blocks(
        {"validation_result": _invalid_plan()}, plan_rejection_reason="user said no"
    )

    assert REJECTION_MARKER in blocks
    assert BLOCKED_MARKER not in blocks


def test_draft_cancellation_wins_over_the_blocked_directive():
    """Same reasoning: the user knows what they cancelled."""
    state = {
        "validation_result": _invalid_plan(),
        "draft_action_result": {"action": "cancel", "draft_type": "email"},
    }
    blocks = _system_blocks(state)

    assert CANCELLED_MARKER in blocks
    assert BLOCKED_MARKER not in blocks


@pytest.mark.parametrize(
    "code",
    [
        ToolErrorCode.UNAUTHORIZED,
        ToolErrorCode.CONFIGURATION_ERROR,
        ToolErrorCode.MISSING_REQUIRED_PARAM,
        ToolErrorCode.INTERNAL_ERROR,
    ],
)
def test_every_blocking_cause_produces_a_directive(code):
    """Generalisation: honesty is owed for every refusal, not only for scopes."""
    result = ValidationResult(
        is_valid=False,
        errors=[
            ValidationIssue(
                severity="error",
                code=code,
                message="blocked",
                step_index=0,
                tool_name="some_tool",
            )
        ],
        total_steps=1,
    )

    assert BLOCKED_MARKER in _system_blocks({"validation_result": result})
