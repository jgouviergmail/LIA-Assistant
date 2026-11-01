"""Run some steps of a plan — and every step they need — before the rest of it.

A question asked before a plan acts must stand on real results: the FOR_EACH
confirmation counts the items its providers really return, and « which one? »
lists the items a lookup really found (ADR-367 amendment). Both run those
steps first, in a sub-plan of the same plan, and resume the whole plan from
what they returned (``initial_completed_steps``) — nothing runs twice.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from langchain_core.runnables import RunnableConfig

from src.core.constants import FOR_EACH_PRE_EXECUTION_METADATA_KEY
from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

if TYPE_CHECKING:
    from src.domains.agents.orchestration.parallel_executor import ParallelExecutionResult

__all__ = ["execute_steps_first", "steps_needed_first"]


def steps_needed_first(plan: ExecutionPlan, step_ids: Iterable[str]) -> list[str]:
    """The steps to run first: those named and every step they depend on, in plan order.

    Args:
        plan: The plan.
        step_ids: The steps whose results are needed first.

    Returns:
        Their ids and their dependencies' ids, in the plan's order.
    """
    graph = DependencyGraph(plan)
    wanted: set[str] = set()
    for step_id in step_ids:
        wanted |= {step_id, *graph.get_all_dependencies(step_id)}
    return [step.step_id for step in plan.steps if step.step_id in wanted]


async def execute_steps_first(
    plan: ExecutionPlan,
    step_ids: Iterable[str],
    config: RunnableConfig,
    run_id: str,
    *,
    initial_registry: dict[str, Any] | None = None,
    turn_id: int | None = None,
) -> ParallelExecutionResult | None:
    """Execute the named steps and their dependencies as a sub-plan of ``plan``.

    Args:
        plan: The full plan.
        step_ids: The steps whose results are needed first.
        config: The run's config.
        run_id: The run.
        initial_registry: The registry the steps resolve references against.
        turn_id: The current turn, stamped on the items they produce.

    Returns:
        The sub-plan's result, or None when there is nothing to run.
    """
    from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel

    wanted = set(steps_needed_first(plan, step_ids))
    steps = [step for step in plan.steps if step.step_id in wanted]
    if not steps:
        return None
    metadata = plan.metadata or {}
    sub_plan = ExecutionPlan(
        plan_id=f"{plan.plan_id}_pre_exec",
        user_id=plan.user_id,
        steps=steps,
        # What a tool reads of its plan: the domains, the intent, the goal.
        metadata={
            FOR_EACH_PRE_EXECUTION_METADATA_KEY: True,
            "domains": metadata.get("domains"),
            "intent": metadata.get("intent"),
            "user_goal": metadata.get("user_goal"),
        },
    )
    return await execute_plan_parallel(
        execution_plan=sub_plan,
        config=config,
        run_id=run_id,
        initial_registry=initial_registry,
        turn_id=turn_id,
    )
