"""The script-skill runner is handed an ACTIVATED skill, and the history only when it resumes one.

The ReactSubAgentRunner spawns a fresh sub-agent every turn with no memory.
Multi-turn skill dialogues (skill-generator: clarify → answer → generate)
therefore need the windowed conversation history embedded in the runner task
(S5). Measured in production 2026-09-20 (run at 18:00): the same block on a
ONE-SHOT script skill (tic-tac-toe) carried an earlier text game, the model
treated the request as a reply within that dialogue, ran no script and
answered in prose — which the node then dropped in silence. So:

- the skill is activated in Python and its instructions travel in the task
  (`<skill_instructions>`), the activation tool is not bound to the runner;
- history present AND the skill declares ``dialogue`` → a
  ``<conversation_history>`` block; a one-shot skill never gets one;
- a runner that called no tool is said (log + counter) and the instructions
  fall back to the passive injection instead of vanishing.
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from src.infrastructure.observability.metrics_registry import skill_runner_outcomes_total

# The nodes package __init__ re-exports the *function* response_node, which
# shadows the module attribute — resolve the module explicitly.
rn = importlib.import_module("src.domains.agents.nodes.response_node")

pytestmark = pytest.mark.unit

_INSTRUCTIONS = "<skill_content>Run render_game.py with no parameters.</skill_content>"


def _runner_capture(captured: dict[str, Any], iterations: int = 1) -> MagicMock:
    """Build a ReactSubAgentRunner double that records run() kwargs."""
    result = MagicMock()
    result.iteration_count = iterations
    result.final_message = "done"
    result.accumulated_registry = {}
    result.duration_ms = 5

    runner = MagicMock()

    async def _run(**kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return result

    runner.run = AsyncMock(side_effect=_run)
    return runner


async def _invoke(
    conversation_history: str, *, dialogue: bool = True, iterations: int = 1
) -> tuple[dict[str, Any], Any, list[dict[str, Any]]]:
    """Drive _activate_response_skills down the runner branch with mocks."""
    captured: dict[str, Any] = {}

    state = {
        "messages": [],
        "query_intelligence": {"detected_skill_name": "skill-generator"},
        "agent_results": {},
    }
    config = {"configurable": {"langgraph_user_id": "u1", "thread_id": "t1"}, "metadata": {}}

    skill_data = {
        "name": "skill-generator",
        "scripts": ["validate_skill.py"],
        "dialogue": dialogue,
    }

    registry = MagicMock()
    registry.get_store.return_value = MagicMock()

    with (
        patch.object(rn, "settings") as mock_settings,
        patch.object(rn, "_get_skill_data", return_value=skill_data),
        patch(
            "src.domains.agents.tools.react_runner.ReactSubAgentRunner",
            return_value=_runner_capture(captured, iterations),
        ),
        patch(
            "src.domains.agents.registry.agent_registry.get_global_registry",
            return_value=registry,
        ),
        patch("src.domains.skills.activation.activate_skill", return_value=_INSTRUCTIONS),
        patch("src.core.context.active_skills_ctx") as mock_ctx,
        patch("src.domains.skills.cache.SkillsCache") as mock_cache,
        structlog.testing.capture_logs() as logs,
    ):
        mock_settings.skills_enabled = True
        mock_ctx.get.return_value = None
        mock_cache.get_always_loaded.return_value = []

        result = await rn._activate_response_skills(
            state,  # type: ignore[arg-type]
            config,  # type: ignore[arg-type]
            "run-1",
            last_user_message="oui, archétype Advisory",
            conversation_history=conversation_history,
            current_turn_registry=None,
            react_result=None,
        )
    return captured, result, logs


def _outcome(outcome: str) -> float:
    return float(skill_runner_outcomes_total.labels(outcome=outcome)._value.get())


class TestSkillRunnerReceivesHistory:
    async def test_a_dialogue_skill_gets_the_history_block(self) -> None:
        history = "User: crée-moi une skill météo\nAssistant: Quel format veux-tu ?"
        captured, _, _ = await _invoke(history, dialogue=True)

        assert captured, "runner.run was not invoked"
        task = captured["task"]
        assert "<conversation_history>" in task
        assert "crée-moi une skill météo" in task
        # The latest message stays the primary instruction.
        assert "oui, archétype Advisory" in task

    async def test_a_one_shot_skill_never_gets_the_history_block(self) -> None:
        history = "User: je veux jouer au morpion\nAssistant: 1 | 2 | 3 ..."
        captured, _, _ = await _invoke(history, dialogue=False)

        assert captured, "runner.run was not invoked"
        assert "<conversation_history>" not in captured["task"]
        assert "oui, archétype Advisory" in captured["task"]

    async def test_no_history_no_block(self) -> None:
        captured, _, _ = await _invoke("", dialogue=True)

        assert captured, "runner.run was not invoked"
        assert "<conversation_history>" not in captured["task"]


class TestSkillRunnerIsHandedAnActivatedSkill:
    async def test_the_instructions_travel_in_the_task_and_the_activation_tool_stays_out(
        self,
    ) -> None:
        captured, _, _ = await _invoke("", dialogue=False)

        task = captured["task"]
        assert "<skill_instructions>" in task and _INSTRUCTIONS in task
        bound = {t.name for t in captured["tools"]}
        assert "run_skill_script" in bound and "read_skill_resource" in bound
        assert "activate_skill_tool" not in bound

    async def test_a_runner_that_called_no_tool_is_said_and_falls_back_to_the_instructions(
        self,
    ) -> None:
        before = _outcome("no_tool_call")
        _, result, logs = await _invoke("", dialogue=False, iterations=0)

        assert result.skill_react_response is None
        assert _INSTRUCTIONS in result.skills_context
        assert [e for e in logs if e["event"] == "skill_runner_no_tool_call"]
        assert _outcome("no_tool_call") == before + 1

    async def test_a_runner_that_ran_its_tools_is_counted_as_such(self) -> None:
        before = _outcome("tools_called")
        _, result, _ = await _invoke("", dialogue=False, iterations=2)

        assert result.skill_react_response == "done"
        assert _outcome("tools_called") == before + 1
