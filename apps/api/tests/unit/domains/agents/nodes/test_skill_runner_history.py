"""S5 — the script-skill runner must receive the conversation history.

The ReactSubAgentRunner spawns a fresh sub-agent every turn with no memory.
Multi-turn skill dialogues (skill-generator: clarify → answer → generate)
therefore need the windowed conversation history embedded in the runner task.
These tests pin that contract on ``_activate_response_skills``:

- history present → task contains a ``<conversation_history>`` block
- history empty → no block (one-shot skills unchanged)
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The nodes package __init__ re-exports the *function* response_node, which
# shadows the module attribute — resolve the module explicitly.
rn = importlib.import_module("src.domains.agents.nodes.response_node")

pytestmark = pytest.mark.unit


def _runner_capture(captured: dict[str, Any]) -> MagicMock:
    """Build a ReactSubAgentRunner double that records run() kwargs."""
    result = MagicMock()
    result.iteration_count = 1
    result.final_message = "done"
    result.accumulated_registry = {}
    result.duration_ms = 5

    runner = MagicMock()

    async def _run(**kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return result

    runner.run = AsyncMock(side_effect=_run)
    return runner


async def _invoke(conversation_history: str) -> dict[str, Any]:
    """Drive _activate_response_skills down the runner branch with mocks."""
    captured: dict[str, Any] = {}

    state = {
        "messages": [],
        "query_intelligence": {"detected_skill_name": "skill-generator"},
        "agent_results": {},
    }
    config = {"configurable": {"langgraph_user_id": "u1", "thread_id": "t1"}, "metadata": {}}

    skill_data = {"name": "skill-generator", "scripts": ["validate_skill.py"]}

    registry = MagicMock()
    registry.get_store.return_value = MagicMock()

    with (
        patch.object(rn, "settings") as mock_settings,
        patch.object(rn, "_get_skill_data", return_value=skill_data),
        patch(
            "src.domains.agents.tools.react_runner.ReactSubAgentRunner",
            return_value=_runner_capture(captured),
        ),
        patch(
            "src.domains.agents.registry.agent_registry.get_global_registry",
            return_value=registry,
        ),
        patch("src.core.context.active_skills_ctx") as mock_ctx,
        patch("src.domains.skills.cache.SkillsCache") as mock_cache,
    ):
        mock_settings.skills_enabled = True
        mock_ctx.get.return_value = None
        mock_cache.get_always_loaded.return_value = []

        await rn._activate_response_skills(
            state,  # type: ignore[arg-type]
            config,  # type: ignore[arg-type]
            "run-1",
            last_user_message="oui, archétype Advisory",
            conversation_history=conversation_history,
            current_turn_registry=None,
            react_result=None,
        )
    return captured


class TestSkillRunnerReceivesHistory:
    @pytest.mark.asyncio
    async def test_history_block_embedded_in_task(self) -> None:
        history = "User: crée-moi une skill météo\nAssistant: Quel format veux-tu ?"
        captured = await _invoke(history)

        assert captured, "runner.run was not invoked"
        task = captured["task"]
        assert "<conversation_history>" in task
        assert "crée-moi une skill météo" in task
        # The latest message stays the primary instruction.
        assert "oui, archétype Advisory" in task

    @pytest.mark.asyncio
    async def test_no_history_no_block(self) -> None:
        captured = await _invoke("")

        assert captured, "runner.run was not invoked"
        task = captured["task"]
        assert "<conversation_history>" not in task
        assert "oui, archétype Advisory" in task
