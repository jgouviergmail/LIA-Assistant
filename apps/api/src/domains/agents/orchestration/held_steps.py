"""Which steps of a plan wait for an answer the person has not given yet (spec 2026-10-29 D7).

A step that returned DRAFTS is pending: its act waits for the person's approval,
and what it returned is the draft, not the act's result. A step that READS that
result — through its parameters, its condition or the list it iterates over —
would run on a placeholder: it is HELD instead, as is a step ordered after a held
one (it cannot run before it). A step the planner explicitly ORDERS after a
pending step (``depends_on``) is held too, but by ORDER only: it reads no
placeholder, so it waits for the decision and then runs whatever it was (the
resume tells the two apart, ``held_by_order_only``). Implicit sequential chaining
holds nothing: only an order the planner wrote does.

Measured 2026-10-29 (probe « dependents »): the reading step ran on the draft's
preview, or the plan logged a dependency DEADLOCK. Measured 2026-10-30 (full turn
on Docker dev): « supprime la note n2, puis montre-moi la liste à jour » ordered
the second read after the deletion without reading it — it ran before the act.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping

from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.for_each_utils import extract_step_references
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    for_each_parent_id,
)


def held_steps(plan: ExecutionPlan, pending: Mapping[str, list[str]]) -> dict[str, list[str]]:
    """Every step that must wait, with the drafts it waits for.

    Args:
        plan: The plan as it runs (FOR_EACH steps possibly expanded).
        pending: Each step that returned drafts, with their draft ids.

    Returns:
        Each held step mapped to the draft ids it waits for, in plan order;
        empty when nothing waits.
    """
    return _hold(plan, pending)[0]


def held_by_order_only(plan: ExecutionPlan, pending: Mapping[str, list[str]]) -> set[str]:
    """The held steps that read no pending result: they wait for the decision alone.

    Args:
        plan: The plan as it runs.
        pending: Each step that returned drafts, with their draft ids.

    Returns:
        The held steps whose every path to a pending step is an order the
        planner wrote, or a read of a step held that way.
    """
    held, by_data = _hold(plan, pending)
    return set(held) - by_data


def told_after_the_answer(
    plan: ExecutionPlan, pending: Mapping[str, list[str]], ran: Collection[str]
) -> list[str]:
    """The steps that ran BESIDE the pending acts: the answer tells them (spec D5).

    A step a pending act reads or follows — transitively — served that act alone
    (a lookup of the id it acts on): the act's own card says it. Every other step
    that ran is work the person asked for, which a decision answered by its card
    alone would never mention.

    Args:
        plan: The plan as it ran.
        pending: Each step that returned drafts, with their draft ids.
        ran: The ids of the steps that ran (FOR_EACH items included).

    Returns:
        Those steps, in plan order; empty when nothing is pending.
    """
    if not pending:
        return []
    acts = {for_each_parent_id(step_id) or step_id for step_id in pending}
    steps = {step.step_id: step for step in plan.steps}
    served: set[str] = set()
    frontier = [steps[act] for act in acts if act in steps]
    while frontier:
        step = frontier.pop()
        for source in (_data_sources(step) | set(step.depends_on)) - served:
            if source in steps:
                served.add(source)
                frontier.append(steps[source])
    return [
        step.step_id
        for step in plan.steps
        if step.step_id in ran and step.step_id not in acts and step.step_id not in served
    ]


def _hold(
    plan: ExecutionPlan, pending: Mapping[str, list[str]]
) -> tuple[dict[str, list[str]], set[str]]:
    """The held steps with their blockers, and those held by a pending RESULT."""
    if not pending:
        return {}, set()
    waiting = _waiting_results(pending)
    dependencies = DependencyGraph(plan).dependencies
    position = {step.step_id: index for index, step in enumerate(plan.steps)}
    held: dict[str, list[str]] = {}
    by_data: set[str] = set()
    while True:
        # Recomputed whole until stable: a step's class may depend on a step
        # listed after it, and both sets only grow, so this ends.
        now: dict[str, list[str]] = {}
        now_by_data: set[str] = set()
        for step in plan.steps:
            if step.step_id in pending:
                continue
            verdict = _step_hold(
                step, dependencies.get(step.step_id, set()), waiting, held, by_data
            )
            if verdict is None:
                continue
            ordered, by_result = verdict
            ordered.sort(key=lambda s: (position.get(s, -1), s))
            now[step.step_id] = _drafts_of(ordered, waiting, held)
            if by_result:
                now_by_data.add(step.step_id)
        if now == held and now_by_data == by_data:
            return held, by_data
        held, by_data = now, now_by_data


def _step_hold(
    step: ExecutionStep,
    depends: set[str],
    waiting: Mapping[str, list[str]],
    held: Mapping[str, list[str]],
    by_data: set[str],
) -> tuple[list[str], bool] | None:
    """What one step waits on, and whether on a RESULT — None when on nothing.

    It waits on a pending result or a held step it READS, on a held step it
    follows, and on a pending step the planner explicitly ordered it after.
    """
    reads = {s for s in _data_sources(step) if s in waiting or s in held}
    follows = {s for s in depends if s in held} | {s for s in step.depends_on if s in waiting}
    if not reads and not follows:
        return None
    by_result = bool(reads & (waiting.keys() | by_data) or follows & by_data)
    return list(reads | follows), by_result


def _drafts_of(
    sources: list[str], waiting: Mapping[str, list[str]], held: Mapping[str, list[str]]
) -> list[str]:
    """The draft ids the given sources wait for, each once, in their order."""
    drafts = [draft for source in sources for draft in (waiting.get(source) or held[source])]
    return list(dict.fromkeys(drafts))


def _waiting_results(pending: Mapping[str, list[str]]) -> dict[str, list[str]]:
    """The results that are drafts: each pending step's, and its FOR_EACH aggregate's."""
    waiting: dict[str, list[str]] = {}
    for step_id, drafts in pending.items():
        for source in (step_id, for_each_parent_id(step_id)):
            if source is not None:
                waiting[source] = list(dict.fromkeys([*waiting.get(source, []), *drafts]))
    return waiting


def _data_sources(step: ExecutionStep) -> set[str]:
    """The steps whose RESULT this step reads (the dependency graph's own reader)."""
    read = json.dumps(step.parameters or {}) + (step.condition or "") + (step.for_each or "")
    return extract_step_references(read)


def held_now(
    plan: ExecutionPlan,
    drafts: list[dict[str, object]],
    completed: Mapping[str, object],
) -> dict[str, list[str]]:
    """The steps that must wait, given the drafts the run has collected so far.

    Args:
        plan: The plan as it runs.
        drafts: The drafts collected, each naming its step (``drafts_of``).
        completed: The steps that already ran — never held.

    Returns:
        The held steps not yet run, with the draft ids each waits for.
    """
    pending: dict[str, list[str]] = {}
    for draft in drafts:
        step_id, draft_id = draft.get("step_id"), draft.get("draft_id")
        if isinstance(step_id, str) and isinstance(draft_id, str):
            pending.setdefault(step_id, []).append(draft_id)
    return {
        step_id: blockers
        for step_id, blockers in held_steps(plan, pending).items()
        if step_id not in completed
    }
