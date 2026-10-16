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

from src.core.config import settings
from src.core.i18n import get_language_name
from src.domains.agents.nodes.response_node import _build_response_chain
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.validator import ValidationIssue, ValidationResult
from src.domains.agents.tools.common import ToolErrorCode

BLOCKED_MARKER = "PLAN BLOCKED BY VALIDATION"
REJECTION_MARKER = "PLAN REJECTION"
CANCELLED_MARKER = "DRAFT"

#: A language that is not the instance default, so nothing passes by chance.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)


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
            user_language=_PERSON,
            llm=MagicMock(),
            performed_actions_block="",
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


@pytest.mark.parametrize(
    ("state", "rejection"),
    [
        ({"validation_result": _invalid_plan()}, None),
        ({"validation_result": _invalid_plan()}, "user said no"),
        ({"draft_action_result": {"action": "cancel", "draft_type": "email"}}, None),
    ],
    ids=["plan_blocked", "plan_rejection", "draft_cancelled"],
)
def test_each_directive_names_the_person_s_language(state: dict, rejection: str | None):
    """The model is told the language's NAME, never its code (ADR-323)."""
    blocks = _system_blocks(state, plan_rejection_reason=rejection)

    assert f"ONLY in {get_language_name(_PERSON)}" in blocks
    assert f"ONLY in {_PERSON}" not in blocks


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


# =========================================================================
# The verdict is weighed against what actually ran (defect 2026-07-31)
# =========================================================================


def _ran_plan(tool_name: str = "get_emails_tool") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="smart_unknown",
        user_id="u1",
        session_id="s1",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name=tool_name,
                parameters={"max_results": 20},
            )
        ],
    )


def _capped_plan() -> ValidationResult:
    """The verbatim validator verdict of request 83c98053."""
    return ValidationResult(
        is_valid=False,
        errors=[
            ValidationIssue(
                severity="error",
                code=ToolErrorCode.CONSTRAINT_VIOLATION,
                message="Parameter 'max_results' value 20 > max 10",
                step_index=0,
                tool_name="get_emails_tool",
            )
        ],
        total_steps=1,
    )


def test_a_capability_that_ran_is_never_declared_blocked():
    """Production 83c98053: ten emails in the registry, "retrieval blocked".

    The step ran and returned; only the plan carried a verdict nobody acted
    on. Telling the user their request was blocked — and to go fix an email
    connector that was healthy — is the same invented diagnosis this directive
    exists to prevent, pointing the other way.
    """
    blocks = _system_blocks(
        {
            "validation_result": _capped_plan(),
            "execution_plan": _ran_plan(),
            "completed_steps": {"step_1": {"emails": [{"id": "a"}], "total": 10}},
        }
    )

    assert BLOCKED_MARKER not in blocks


def test_a_capability_that_ran_and_failed_is_never_declared_blocked():
    """RC1.2 (production 2026-10-07): one fact, one channel.

    The step ran and failed; its failure belongs to the runtime failures
    directive. Declared « blocked » as well, it reached the model twice with
    two causes — and the « blocked » one, marked authoritative, won.
    """
    blocks = _system_blocks(
        {
            "validation_result": _capped_plan(),
            "execution_plan": _ran_plan(),
            "completed_steps": {"step_1": {"success": False, "error": "boom"}},
        }
    )

    assert BLOCKED_MARKER not in blocks


def test_a_capability_that_never_ran_is_still_declared_blocked():
    """The founding case: the step never reached execution."""
    blocks = _system_blocks(
        {
            "validation_result": _capped_plan(),
            "execution_plan": _ran_plan(),
            "completed_steps": {},
        }
    )

    assert BLOCKED_MARKER in blocks


def test_a_turn_without_execution_state_keeps_reporting_blockers():
    """HITL resumes and ReAct turns carry no completed_steps — never hide."""
    blocks = _system_blocks({"validation_result": _invalid_plan()})

    assert BLOCKED_MARKER in blocks


def test_only_the_capability_that_did_not_run_is_named():
    """A partial turn must not be reported as a total failure."""
    plan = ExecutionPlan(
        plan_id="p",
        user_id="u1",
        session_id="s1",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name="get_emails_tool",
                parameters={},
            ),
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.TOOL,
                agent_name="calendar_agent",
                tool_name="get_events_tool",
                parameters={},
            ),
        ],
    )
    verdict = ValidationResult(
        is_valid=False,
        errors=[
            ValidationIssue(
                severity="error",
                code=ToolErrorCode.CONSTRAINT_VIOLATION,
                message="Parameter 'max_results' value 20 > max 10",
                step_index=0,
                tool_name="get_emails_tool",
            ),
            ValidationIssue(
                severity="error",
                code=ToolErrorCode.UNAUTHORIZED,
                message="Missing required scopes",
                step_index=1,
                tool_name="get_events_tool",
            ),
        ],
        total_steps=2,
    )

    blocks = _system_blocks(
        {
            "validation_result": verdict,
            "execution_plan": plan,
            "completed_steps": {"step_1": {"emails": []}},
        }
    )

    assert BLOCKED_MARKER in blocks
    assert "get_events_tool" in blocks
    assert "get_emails_tool" not in blocks


# =========================================================================
# One fact, one channel (RC1.2, production 2026-10-07)
# =========================================================================


def _verdict(
    *tool_names: str, code: ToolErrorCode = ToolErrorCode.UNAUTHORIZED
) -> ValidationResult:
    return ValidationResult(
        is_valid=False,
        errors=[
            ValidationIssue(
                severity="error",
                code=code,
                message="Missing required scopes",
                step_index=index,
                tool_name=name,
            )
            for index, name in enumerate(tool_names)
        ],
        total_steps=len(tool_names),
    )


def _plan_of(*tool_names: str) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p",
        user_id="u1",
        session_id="s1",
        steps=[
            ExecutionStep(
                step_id=f"step_{index + 1}",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name=name,
                parameters={},
            )
            for index, name in enumerate(tool_names)
        ],
    )


async def _honesty_block(state: dict, monkeypatch: pytest.MonkeyPatch) -> str:
    """The runtime failures directive the response node would add to the turn."""
    from src.domains.agents.services.runtime_failure_directive import build_run_honesty_block

    monkeypatch.setattr(settings, "diagnostics_enabled", False)
    return await build_run_honesty_block(state)


@pytest.mark.asyncio
async def test_the_failed_reply_of_run_b148e908_is_told_by_the_failures_directive_alone(
    monkeypatch: pytest.MonkeyPatch,
):
    """20:25: two contact reads succeeded, the reply failed on its reference.

    The answer said the reply capability was « not connected or authorized »:
    the verdict of a step that RAN. Its failure is now said once, by the
    directive that carries the step's own code.
    """
    state = {
        "validation_result": _verdict("get_contacts_tool", "get_contacts_tool", "reply_email_tool"),
        "execution_plan": _plan_of("get_contacts_tool", "get_contacts_tool", "reply_email_tool"),
        "completed_steps": {
            "step_1": {"contacts": [{"id": "c1"}]},
            "step_2": {"contacts": [{"id": "c2"}]},
            "step_3": {
                "success": False,
                "error": "reference_resolution_failed",
                "error_code": ToolErrorCode.INVALID_INPUT.value,
            },
        },
    }

    assert BLOCKED_MARKER not in _system_blocks(state)
    honesty = await _honesty_block(state, monkeypatch)
    assert '"tool": "reply_email_tool"' in honesty
    assert f'"error_code": "{ToolErrorCode.INVALID_INPUT.value}"' in honesty


@pytest.mark.asyncio
async def test_a_mailbox_nobody_connected_is_still_said_without_the_blocked_directive(
    monkeypatch: pytest.MonkeyPatch,
):
    """18:13: no mail connector at all — the honest answer must survive RC1.2."""
    code = ToolErrorCode.CONNECTOR_NOT_ACTIVATED.value
    state = {
        "validation_result": _verdict("get_emails_tool"),
        "execution_plan": _plan_of("get_emails_tool"),
        "completed_steps": {
            "step_1": {
                "success": False,
                "error": "No email service is activated.",
                "error_code": code,
            }
        },
    }

    assert BLOCKED_MARKER not in _system_blocks(state)
    honesty = await _honesty_block(state, monkeypatch)
    assert f'"error_code": "{code}"' in honesty


@pytest.mark.asyncio
async def test_the_refused_relay_of_request_2ecc670c_is_told_by_the_failures_directive(
    monkeypatch: pytest.MonkeyPatch,
):
    """2026-08-17: the relay was refused; it must never read as delivered NOR as blocked."""
    state = {
        "validation_result": _verdict(
            "send_peer_message_tool", code=ToolErrorCode.CONSTRAINT_VIOLATION
        ),
        "execution_plan": _plan_of("send_peer_message_tool"),
        "completed_steps": {
            "step_1": {
                "success": False,
                "error": "The message exceeds 2000 characters.",
                "error_code": ToolErrorCode.INVALID_INPUT.value,
            }
        },
    }

    assert BLOCKED_MARKER not in _system_blocks(state)
    honesty = await _honesty_block(state, monkeypatch)
    assert "The message exceeds 2000 characters." in honesty
    assert '"tool": "send_peer_message_tool"' in honesty
