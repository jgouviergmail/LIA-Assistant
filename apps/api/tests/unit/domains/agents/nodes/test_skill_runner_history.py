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

A THIRD-PARTY skill (ADR-327) always goes through the runner, isolated on its
own skill: no import tool, the scope set for the run only, its answer drawn by
``untrusted_markdown``, and never a passive fallback — its words never reach
the response prompt, nor does it load itself as an always-loaded skill.
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from src.core.context import bind_skill_context, isolated_skill_ctx, reset_skill_context
from src.infrastructure.observability.metrics_registry import skill_runner_outcomes_total

# The nodes package __init__ re-exports the *function* response_node, which
# shadows the module attribute — resolve the module explicitly.
rn = importlib.import_module("src.domains.agents.nodes.response_node")

pytestmark = pytest.mark.unit

_INSTRUCTIONS = "<skill_content>Run render_game.py with no parameters.</skill_content>"


def _runner_capture(
    captured: dict[str, Any],
    iterations: int = 1,
    final: str = "done",
    error: Exception | None = None,
) -> MagicMock:
    """Build a ReactSubAgentRunner double that records run() kwargs and its scope."""
    result = MagicMock()
    result.iteration_count = iterations
    result.final_message = final
    result.accumulated_registry = {}
    result.duration_ms = 5

    runner = MagicMock()

    async def _run(**kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        captured["isolated"] = isolated_skill_ctx.get()
        if error is not None:
            raise error
        return result

    runner.run = AsyncMock(side_effect=_run)
    return runner


async def _invoke(
    conversation_history: str,
    *,
    dialogue: bool = True,
    iterations: int = 1,
    scripts: bool = True,
    resources: list[str] | None = None,
    third_party: bool = False,
    final: str = "done",
    error: Exception | None = None,
    always_loaded: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], Any, list[dict[str, Any]]]:
    """Drive _activate_response_skills down the runner branch with mocks.

    ``skill-generator`` resolves to a system skill, or to the person's own
    third-party skill when ``third_party`` — bound as the request binds it.
    """
    captured: dict[str, Any] = {}

    state = {
        "messages": [],
        "query_intelligence": {"detected_skill_name": "skill-generator"},
        "agent_results": {},
    }
    config = {"configurable": {"langgraph_user_id": "u1", "thread_id": "t1"}, "metadata": {}}

    skill_data = {
        "name": "skill-generator",
        "scripts": ["validate_skill.py"] if scripts else [],
        "all_resources": resources or [],
        "dialogue": dialogue,
    }
    entry = {"name": "skill-generator", "scope": "user" if third_party else "admin"}
    names = {"skill-generator"} | {s["name"] for s in always_loaded or []}
    third_party_names = frozenset({"skill-generator"} if third_party else set()) | frozenset(
        s["name"] for s in always_loaded or [] if s.get("scope") == "user"
    )

    registry = MagicMock()
    registry.get_store.return_value = MagicMock()

    with (
        patch.object(rn, "settings") as mock_settings,
        patch.object(rn, "_get_skill_data", return_value=skill_data),
        patch(
            "src.domains.agents.tools.react_runner.ReactSubAgentRunner",
            return_value=_runner_capture(captured, iterations, final, error),
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
        mock_cache.get_always_loaded.return_value = always_loaded or []
        mock_cache.get_by_name_for_user.return_value = entry
        tokens = bind_skill_context(names, third_party_names)
        try:
            result = await rn._activate_response_skills(
                state,  # type: ignore[arg-type]
                config,  # type: ignore[arg-type]
                "run-1",
                last_user_message="oui, archétype Advisory",
                conversation_history=conversation_history,
                current_turn_registry=None,
                react_result=None,
            )
        finally:
            reset_skill_context(tokens)
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


class TestASkillThatShipsACommandRuns:
    async def test_a_shell_script_alone_goes_through_the_runner(self) -> None:
        # No Python script, but something under scripts/ to RUN (ADR-327 lot 2):
        # the passive injection would hand the model a command it cannot run.
        captured, _, _ = await _invoke("", scripts=False, resources=["scripts/build.sh"])
        assert captured, "runner.run was not invoked"
        assert "run_skill_command" in {t.name for t in captured["tools"]}

    async def test_a_reference_alone_does_not(self) -> None:
        captured, _, _ = await _invoke("", scripts=False, resources=["references/guide.md"])
        assert not captured


class TestAThirdPartySkillRunsIsolated:
    async def test_it_goes_through_the_runner_even_without_a_script(self) -> None:
        captured, result, _ = await _invoke("", scripts=False, third_party=True)

        assert captured, "runner.run was not invoked"
        assert captured["isolated"] == "skill-generator"
        assert isolated_skill_ctx.get() is None  # the scope ends with the run
        bound = {t.name for t in captured["tools"]}
        assert bound == {"run_skill_script", "run_skill_command", "read_skill_resource"}
        assert _INSTRUCTIONS not in result.skills_context

    async def test_its_answer_is_neutralised_even_without_a_tool_call(self) -> None:
        final = "Chart: ![c](https://collector.example/?d=x) <b>ok</b>"
        _, result, _ = await _invoke("", third_party=True, iterations=0, final=final)

        answer = result.skill_react_response
        assert answer is not None and "<" not in answer and "![" not in answer
        assert result.react_result["final_message"] == answer

    async def test_a_failed_runner_leaves_nothing_of_it_in_the_prompt(self) -> None:
        _, result, _ = await _invoke("", third_party=True, error=RuntimeError("boom"))

        assert result.skill_react_response is None
        assert result.skills_context == ""

    async def test_an_empty_answer_is_no_answer(self) -> None:
        _, result, _ = await _invoke("", third_party=True, final="  ")

        assert result.skill_react_response is None
        assert result.skills_context == ""

    @pytest.mark.parametrize(("scope", "loaded"), [("admin", True), ("user", False)])
    async def test_only_a_skill_written_here_loads_itself_always(
        self, scope: str, loaded: bool
    ) -> None:
        always = [{"name": "house-style", "scope": scope, "always_loaded": True}]
        _, result, _ = await _invoke("", always_loaded=always)

        assert (_INSTRUCTIONS in result.skills_context) is loaded


class TestTheCollectedData:
    """What the plan already fetched this turn travels to the runner, or nothing does."""

    def test_no_result_no_block(self) -> None:
        from src.domains.agents.nodes.response_skill_runner import collected_data_block

        assert collected_data_block({"agent_results": {}}) == ""

    def test_a_summary_is_wrapped_for_the_task(self) -> None:
        from src.domains.agents.nodes import response_skill_runner as runner

        with patch(
            "src.domains.agents.formatters.agent_results.format_agent_results_for_prompt",
            return_value="3 events tomorrow",
        ):
            block = runner.collected_data_block(
                {"agent_results": {"1:plan": {}}, "current_turn_id": 1}
            )
        assert "<collected_data>" in block and "3 events tomorrow" in block
