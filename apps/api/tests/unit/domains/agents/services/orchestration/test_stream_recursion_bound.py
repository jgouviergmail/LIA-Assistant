"""The graph's recursion bound follows the engine the turn runs in (ADR-070).

The loop takes two graph transitions per iteration, the pipeline a handful per
turn, so each gets its own bound. A turn that RESUMES after a question never
meets the router again: it runs in the engine it started with, whatever the
person chose since. Its bound must follow that engine — a loop resumed under the
pipeline's bound stops mid-flight on ``GraphRecursionError``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import REACT_GRAPH_RECURSION_HEADROOM
from src.domains.agents.models import create_initial_state
from src.domains.agents.services.orchestration import service as orchestration_module
from src.domains.agents.services.orchestration import turn_input
from src.domains.agents.services.orchestration.service import OrchestrationService
from tests.fixtures.conversation_cases import conversation_target

pytestmark = pytest.mark.unit


class _CapturingGraph:
    """A graph that records the config each stream was opened with."""

    def __init__(self) -> None:
        self.configs: list[dict[str, Any]] = []

    async def astream(
        self, _input: object, config: dict[str, Any], **_kwargs: object
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        self.configs.append(config)
        yield ("values", {})


class _Tracker:
    async def commit(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _bare_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything but the context builder and the config reduced to nothing."""

    async def no_store() -> None:
        return None

    async def same_context(context: object) -> object:
        return context

    monkeypatch.setattr(orchestration_module, "get_tool_context_store", no_store)
    monkeypatch.setattr(
        orchestration_module, "enrich_config_with_callbacks", lambda config, **_kw: config
    )
    monkeypatch.setattr(orchestration_module, "with_current_extraction_revision", same_context)
    monkeypatch.setattr(turn_input, "prepare_graph_input", lambda *_a: {})


def _loop_bound() -> int:
    return settings.react_agent_max_iterations * 2 + REACT_GRAPH_RECURSION_HEADROOM


async def _bound(*, asked: str, resumed_engine: str | None = None) -> int:
    user_id = uuid4()
    state: dict[str, Any] = dict(create_initial_state(user_id, "session", "run"))
    if resumed_engine is not None:
        state["execution_mode"] = resumed_engine
        state["_interrupt_resume_data"] = {"action": "confirm", "draft_id": "draft-1"}
    graph = _CapturingGraph()
    async for _mode, _chunk in OrchestrationService().execute_graph_stream(
        graph=graph,
        state=state,  # type: ignore[arg-type]
        target=conversation_target(user_id, uuid4()),
        session_id="session",
        run_id="run",
        tool_deps=None,
        tracker=_Tracker(),
        user_execution_mode=asked,
    ):
        pass
    assert len(graph.configs) == 1
    return int(graph.configs[0]["recursion_limit"])


async def test_a_turn_asked_for_the_loop_gets_the_loops_room() -> None:
    loop_bound = _loop_bound()
    assert await _bound(asked="react") == loop_bound


async def test_a_turn_asked_for_the_pipeline_keeps_the_pipelines_bound() -> None:
    pipeline_bound = settings.agent_max_iterations
    assert await _bound(asked="pipeline") == pipeline_bound


async def test_a_resumed_loop_keeps_its_room_after_the_person_chose_the_pipeline() -> None:
    loop_bound = _loop_bound()
    assert await _bound(asked="pipeline", resumed_engine="react") == loop_bound


async def test_a_resumed_pipeline_keeps_its_bound_after_the_person_chose_the_loop() -> None:
    pipeline_bound = settings.agent_max_iterations
    assert await _bound(asked="react", resumed_engine="pipeline") == pipeline_bound
