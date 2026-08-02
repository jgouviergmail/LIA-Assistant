"""ADR-083 — post-resolution cap on delegate_to_sub_agent_tool.instruction.

After $ref resolution, the resolved `instruction` of a delegate step is
re-validated against `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED`. Above the cap,
the step fails with INVALID_INPUT — the planner's "shove raw data via $ref"
anti-pattern is blocked at the only point where the resolved size is known.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domains.agents.orchestration.parallel_executor import _execute_tool_step
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.tools.common import ToolErrorCode


def _delegate_step(instruction: str) -> ExecutionStep:
    """Build a TOOL step for delegate_to_sub_agent_tool with the given literal instruction.

    Using a literal (no $ref) keeps the test focused on the cap, not the resolver.
    """
    return ExecutionStep(
        step_id="step_1",
        step_type=StepType.TOOL,
        tool_name="delegate_to_sub_agent_tool",
        agent_name="sub_agent_agent",
        description="delegate",
        parameters={"expertise": "x", "instruction": instruction},
    )


def _other_step(instruction_like_value: str) -> ExecutionStep:
    """A non-delegate TOOL step (search_emails_tool) carrying a long string param.

    Used to verify the cap is scoped to delegate_to_sub_agent_tool only.
    """
    return ExecutionStep(
        step_id="step_1",
        step_type=StepType.TOOL,
        tool_name="search_emails_tool",
        agent_name="email_agent",
        description="search",
        parameters={"query": instruction_like_value},
    )


def _fake_config(user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "configurable": {
            "user_id": user_id,
            "thread_id": "thread_abc",
            "user_timezone": "Europe/Paris",
            "user_language": "fr",
        },
        "metadata": {},
        "callbacks": [],
    }


@pytest.fixture
def _settings_small_cap():
    """Patch settings with a low cap to make tests deterministic."""
    with patch("src.core.config.get_settings") as mock:
        mock.return_value = SimpleNamespace(subagent_instruction_max_tokens_resolved=100)
        yield mock


@pytest.fixture
def _settings_default_cap():
    """Patch settings with the production default."""
    with patch("src.core.config.get_settings") as mock:
        mock.return_value = SimpleNamespace(subagent_instruction_max_tokens_resolved=3000)
        yield mock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oversized_resolved_instruction_returns_invalid_input(_settings_small_cap):
    """Instruction whose token estimate (chars // 4) exceeds the cap → INVALID_INPUT."""
    # 100 tokens cap → ~400 chars. We blow well past it.
    huge_instruction = "x " * 5_000  # ~10_000 chars ≈ ~2_500 tokens

    step = _delegate_step(huge_instruction)

    result = await _execute_tool_step(
        step=step,
        completed_steps={},
        config=_fake_config(),
        wave_id=0,
        store=None,
    )

    assert result.success is False
    assert result.error_code == ToolErrorCode.INVALID_INPUT
    error_msg = (result.error or "").lower()
    # The error must point at the cap so the planner / log reader knows what happened.
    assert "instruction" in error_msg
    assert "token" in error_msg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_under_cap_instruction_does_not_trigger_cap_error(_settings_default_cap):
    """A reasonably-sized instruction passes the cap check (may fail later — that's fine).

    We assert: IF the step fails, the failure is NOT the cap error. The downstream
    tool invocation may fail for other reasons in this isolated unit test (e.g.,
    no real tool registry / database) — those are out of scope here.
    """
    short_instruction = "Analyse the last 5 emails from Alice and produce a summary."
    step = _delegate_step(short_instruction)

    result = await _execute_tool_step(
        step=step,
        completed_steps={},
        config=_fake_config(),
        wave_id=0,
        store=None,
    )

    # If the step failed (it likely will downstream due to test isolation),
    # the failure must NOT be the cap error.
    if result.success is False:
        error_msg = (result.error or "").lower()
        cap_error_signature = "instruction too large" in error_msg or (
            "instruction" in error_msg and "token" in error_msg and "cap" in error_msg
        )
        assert (
            not cap_error_signature
        ), f"Cap should NOT trigger for a short instruction. Got: {result.error}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cap_does_not_apply_to_non_delegate_tools(_settings_small_cap):
    """The cap is scoped to delegate_to_sub_agent_tool — other tools are not affected.

    A search_emails_tool with a long `query` argument must NOT trigger
    the sub-agent instruction cap.
    """
    huge_query = "x " * 5_000  # would exceed the cap if it were applied
    step = _other_step(huge_query)

    result = await _execute_tool_step(
        step=step,
        completed_steps={},
        config=_fake_config(),
        wave_id=0,
        store=None,
    )

    # If the step failed, it must NOT be due to the sub-agent instruction cap.
    if result.success is False:
        error_msg = (result.error or "").lower()
        assert not (
            "instruction" in error_msg and "token" in error_msg and "cap" in error_msg
        ), f"Cap erroneously applied to non-delegate tool. Got: {result.error}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_instruction_does_not_trigger_cap(_settings_small_cap):
    """Edge case: empty / missing instruction should not be rejected by the cap."""
    step = _delegate_step("")

    result = await _execute_tool_step(
        step=step,
        completed_steps={},
        config=_fake_config(),
        wave_id=0,
        store=None,
    )

    if result.success is False:
        error_msg = (result.error or "").lower()
        cap_error_signature = "instruction" in error_msg and "token" in error_msg
        # An empty instruction may legitimately fail validation downstream — but
        # the failure must not come from the cap.
        assert (
            not cap_error_signature
        ), f"Empty instruction must not trigger cap. Got: {result.error}"
