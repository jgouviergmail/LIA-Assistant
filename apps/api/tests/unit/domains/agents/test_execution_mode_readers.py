"""Every reader of a turn's mode reads the ENGINE, never the request (ADR-070).

Each case installs a context that was asked for the loop while the planner ran
(the loop switched off on the instance; later, an automatic choice). A reader of
the request would report « react »: the sandbox would run a script the pipeline
cannot repair, and the registers would file a pipeline act as a loop's.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.common import ToolErrorCode
from tests.helpers.runtime_context import installed_runtime_context, make_runtime_context

pytestmark = pytest.mark.unit


def _asked_react_ran_pipeline() -> LiaRuntimeContext:
    context = make_runtime_context(requested_execution_mode="react")
    context.turn_engine.settle("pipeline")
    return context


class TestThePythonSandbox:
    """ADR-249: a script runs in the loop only, which can read a traceback."""

    async def test_it_refuses_a_turn_the_planner_runs(self) -> None:
        from src.domains.agents.tools.python_sandbox_tools import _refuse_if_not_runnable

        with patch(
            "src.domains.feature_switches.registry.is_capability_enabled",
            AsyncMock(return_value=True),
        ):
            refusal = await _refuse_if_not_runnable(_asked_react_ran_pipeline())

        assert refusal is not None
        assert refusal.error_code == ToolErrorCode.FORBIDDEN

    async def test_it_lets_the_loop_run(self) -> None:
        from src.domains.agents.tools.python_sandbox_tools import _refuse_if_not_runnable

        context = make_runtime_context(requested_execution_mode="pipeline")
        context.turn_engine.settle("react")
        with patch(
            "src.domains.feature_switches.registry.is_capability_enabled",
            AsyncMock(return_value=True),
        ):
            refusal = await _refuse_if_not_runnable(context)

        assert refusal is None


class TestTheRegisters:
    def test_a_claimed_act_is_filed_under_the_engine(self) -> None:
        from src.domains.agents.effects.runtime import _build_request

        with installed_runtime_context(_asked_react_ran_pipeline()):
            request = _build_request("create_event_tool", "draft", {"title": "x"}, None)

        assert request is not None
        assert request.execution_mode == "pipeline"

    def test_a_consultation_is_filed_under_the_engine(self) -> None:
        from src.domains.agents.effects.treatments import _build

        with installed_runtime_context(_asked_react_ran_pipeline()):
            row = _build("get_events_tool", "read", succeeded=True, duration_ms=3)

        assert row is not None
        assert row.execution_mode == "pipeline"
