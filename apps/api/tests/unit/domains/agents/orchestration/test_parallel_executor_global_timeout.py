"""Unit tests for the global orchestrator timeout (Vague 5 wiring).

`execute_plan_parallel` checks ``settings.task_orchestrator_execution_timeout_seconds``
at the start of each wave-scheduling iteration. When the wall-clock budget is
exceeded:

  - the wave loop stops scheduling new waves (no in-flight cancellation),
  - a structured ``parallel_execution_global_timeout`` warning is logged,
  - the ``lia_parallel_execution_global_timeout_total`` counter is incremented
    with ``plan_outcome=partial|empty`` so operators can quantify how often
    the cap truncates production work.

These tests close the C7 gap previously documented in TIMEOUT_REGISTRY Annex C.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import get_settings
from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)

pytestmark = [pytest.mark.unit]


def _make_plan() -> ExecutionPlan:
    """Minimal valid plan with one TOOL step (never executed in these tests)."""
    return ExecutionPlan(
        plan_id="plan_global_timeout_test",
        user_id="test_user",
        session_id="test_session",
        steps=[
            ExecutionStep(
                step_id="s1",
                step_type=StepType.TOOL,
                agent_name="test_agent",
                tool_name="get_emails_tool",
                parameters={"query": None},
            )
        ],
    )


def _make_config() -> dict[str, Any]:
    """Minimal RunnableConfig — empty configurable section is enough."""
    return {"configurable": {}}


async def _patched_run(timeout_seconds: float) -> Any:
    """Run ``execute_plan_parallel`` with the upstream store + context loader
    stubbed out so the function reaches the wave loop without any external
    dependency.
    """
    s = get_settings()
    with (
        patch.object(s, "task_orchestrator_execution_timeout_seconds", timeout_seconds),
        patch(
            "src.domains.agents.context.store.get_tool_context_store",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.agents.orchestration.parallel_executor._load_execution_contexts",
            new=AsyncMock(return_value={}),
        ),
    ):
        return await execute_plan_parallel(
            execution_plan=_make_plan(),
            config=_make_config(),
            run_id="run_global_timeout_test",
        )


class TestParallelExecutionGlobalTimeout:
    """Soft timeout: counter increments, plan loop stops scheduling new waves."""

    async def test_global_timeout_fires_immediately_with_zero_budget(self) -> None:
        """A 0 s budget guarantees the very first iteration trips the soft check.

        Verifies the Counter increments with ``plan_outcome=empty`` (no step
        had a chance to complete) and the loop returns cleanly with no
        completed steps.
        """
        from src.infrastructure.observability.metrics_agents import (
            parallel_execution_global_timeout_total,
        )

        # Snapshot the counter BEFORE the call so we measure the delta caused
        # by this test, not the lifetime value (which may have been incremented
        # by other tests in the same process).
        before = parallel_execution_global_timeout_total.labels(plan_outcome="empty")._value.get()

        result = await _patched_run(timeout_seconds=0.0)

        after = parallel_execution_global_timeout_total.labels(plan_outcome="empty")._value.get()
        assert after - before == 1, (
            f"Counter should have incremented once on the empty-outcome path "
            f"(before={before}, after={after})"
        )
        # Plan exited cleanly without scheduling any wave.
        assert result.completed_steps == {}

    async def test_global_timeout_does_not_fire_with_generous_budget(self) -> None:
        """A 60 s budget is comfortably above the time it takes to start the
        loop, so the counter must NOT increment for this code path. Note that
        the plan will still fail at execution (no real tools registered) but
        the failure happens AFTER the soft-timeout check, not because of it.
        """
        from src.infrastructure.observability.metrics_agents import (
            parallel_execution_global_timeout_total,
        )

        before_empty = parallel_execution_global_timeout_total.labels(
            plan_outcome="empty"
        )._value.get()
        before_partial = parallel_execution_global_timeout_total.labels(
            plan_outcome="partial"
        )._value.get()

        # The test step references an unregistered tool; the wave will fail or
        # raise — that's fine, we only assert on the global-timeout counter.
        try:
            await _patched_run(timeout_seconds=60.0)
        except Exception:
            # Step-level failures are out of scope for this test.
            pass

        after_empty = parallel_execution_global_timeout_total.labels(
            plan_outcome="empty"
        )._value.get()
        after_partial = parallel_execution_global_timeout_total.labels(
            plan_outcome="partial"
        )._value.get()
        assert after_empty == before_empty
        assert after_partial == before_partial
