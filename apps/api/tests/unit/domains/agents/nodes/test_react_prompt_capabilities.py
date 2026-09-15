"""The ReAct prompt promises only what the turn's tools can do (prompt audit 2026-09-12, A.5).

Measured: ``<Computation>`` promised ``run_python_tool`` unconditionally — on the
public demonstrator the sandbox is off and the tool is not even registered — and
told the model it had « a small number of runs » where the enforced budget is a
setting; and « Mutation tools require user approval automatically » was false for
the 22 tools whose policy is ``reversible``, ``artefact`` or ``sandboxed`` (they
run and are recorded, ADR-263).
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

from src.core.config import settings
from src.domains.agents.nodes.react_prompt import build_system_prompt as _build_system_prompt
from src.domains.agents.nodes.react_prompt import sandbox_available as _sandbox_available

_STATE = {
    "personality_instruction": "friendly",
    "user_timezone": "Europe/Paris",
    "user_language": "fr",
}
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


class TestComputationBlockFollowsTheTools:
    def test_absent_when_the_turn_cannot_compute(self) -> None:
        prompt = _build_system_prompt(_STATE, computation=False)
        assert "<Computation>" not in prompt
        assert "run_python_tool" not in prompt

    def test_present_with_the_enforced_budget_when_it_can(self) -> None:
        prompt = _build_system_prompt(_STATE, computation=True)
        assert "<Computation>" in prompt and "run_python_tool" in prompt
        assert f"{settings.python_sandbox_max_runs_per_turn} run" in prompt
        assert "a small number of runs" not in prompt

    def test_default_promises_nothing(self) -> None:
        """A caller that says nothing gets the conservative prompt."""
        assert "<Computation>" not in _build_system_prompt(_STATE)

    def test_no_placeholder_survives_either_way(self) -> None:
        for computation in (False, True):
            assert not _PLACEHOLDER_RE.findall(
                _build_system_prompt(_STATE, computation=computation)
            )

    async def test_availability_needs_the_tool_bound_and_the_switch_on(self) -> None:
        with patch(
            "src.domains.agents.nodes.react_prompt.is_capability_enabled",
            AsyncMock(return_value=True),
        ) as switch:
            assert await _sandbox_available(["get_emails_tool"]) is False
            switch.assert_not_awaited()  # not bound: the switch is not even read
            assert await _sandbox_available(["get_emails_tool", "run_python_tool"]) is True
        with patch(
            "src.domains.agents.nodes.react_prompt.is_capability_enabled",
            AsyncMock(return_value=False),
        ):
            assert await _sandbox_available(["run_python_tool"]) is False

    def test_no_run_of_blank_lines_when_the_block_is_absent(self) -> None:
        prompt = _build_system_prompt(_STATE).replace("\r\n", "\n")
        assert not re.search(r"\n{3,}", prompt)


class TestApprovalIsTheToolsDecision:
    def test_the_prompt_does_not_promise_a_confirmation_step(self) -> None:
        prompt = _build_system_prompt(_STATE)
        assert "require user approval automatically" not in prompt

    def test_the_prompt_says_who_decides(self) -> None:
        prompt = _build_system_prompt(_STATE)
        assert "decided by the tool" in prompt
        assert "run immediately" in prompt
