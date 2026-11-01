"""« Which one? » before a plan acts on one of several items a lookup found (ADR-367 amendment).

Nothing shown, « reply to Marc's email » is planned as a lookup and an act on
its FIRST result (``orchestration/choice_points.py``). Taking the first of
several is a guess the person never made — the incident of 2026-10-29 in its
other shape. So before any act runs, the orchestrator runs those lookups (reads
only, the FOR_EACH confirmation's own pre-execution) and, when one found
several, hands off to the reference-disambiguation node, which asks which; the
answer narrows that lookup to the chosen item — what ``[0]`` then reads — and
the plan runs from the lookups' results, nothing run twice.

One item found, a lookup the plan reads beyond its first item, a turn nobody
follows (a routine, a ticket, a relayed call), a type with no context
definition: the plan runs as written. A lookup the planner capped at one result
is widened before it runs — a cap of one hides exactly the choice this asks
(measured 2026-10-31: one model family of four capped « reply to Marc's email »
at one, three times in four) — unless the request gives the item's position
(« Marc's LATEST email »): then the cap stands. A position word never silences a
question on several found: « last » is also in « last week ». « None of them »
and a refusal run the plan WITHOUT the act and what depends on it, said as « not
chosen » (``held_plan.not_run``): the lookup did run, so the answer must never
claim nothing was read — the plan-rejection directive says exactly that.

The context lives in ``plan_choice`` (keyed by plan and turn, so a stale one
never matches), returned BEFORE the question as a state update: the node is
re-run from the top on resume, never this orchestrator pass.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Final

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.i18n import resolve_language
from src.core.i18n_patterns import REQUEST_POSITION_WORDS
from src.domains.agents.constants import (
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_PLAN_CHOICE,
    STATE_KEY_RESOLVED_CONTEXT,
)
from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.agents.data_registry.models import RegistryItemType, generate_registry_id
from src.domains.agents.effects.gate import turn_follows_the_conversation
from src.domains.agents.nodes.for_each_preview_identity import replace_filtered_source_items
from src.domains.agents.orchestration.choice_points import ChoicePoint, choice_points
from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.designation_repair import bind_designated_item
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
from src.domains.agents.orchestration.pre_execution import execute_steps_first
from src.domains.agents.registry.catalogue import ACTING_POLICIES
from src.domains.agents.registry.manifest_resolution import resolve_tool_manifest_named
from src.domains.agents.services.planner.parameter_bounds import clamp_to_parameter_schema
from src.domains.agents.tools.runtime_helpers import extract_value_by_path
from src.domains.agents.utils.type_domain_mapping import (
    TOOL_PATTERN_TO_DOMAIN_MAP,
    get_registry_config_for_items_key,
)
from src.domains.shared.answer_lexicon import answer_tokens
from src.domains.shared.text_normalization import fold_name

logger = structlog.get_logger(__name__)

__all__ = [
    "NOT_CHOSEN",
    "ChoicePass",
    "answered_choice",
    "declined_choice",
    "pending_choice",
    "plan_choice_of_turn",
    "settle_plan_choice",
]


#: Why an act was left unrun: several items fit and the person chose none of them.
NOT_CHOSEN: Final = "not chosen"


@dataclass
class ChoicePass:
    """What the orchestrator does with a plan's choices.

    ``ask`` is the state update handing the question off; otherwise the plan
    runs from ``completed`` and ``registry`` — the lookups already run, narrowed
    to the chosen items — without the steps of ``not_run`` (an act nobody chose
    an item for, and what depends on it), each with its reason.
    """

    ask: dict[str, Any] | None = None
    completed: dict[str, dict[str, Any]] = field(default_factory=dict)
    registry: dict[str, Any] = field(default_factory=dict)
    not_run: dict[str, str] = field(default_factory=dict)
    #: The plan bound to the item the person designated, when the planner
    #: looked it up again (``orchestration/designation_repair.py``).
    plan: ExecutionPlan | None = None

    def plan_for(self, plan: ExecutionPlan) -> ExecutionPlan:
        """The plan the turn runs: bound to the designated item when it was repaired."""
        return self.plan if self.plan is not None else plan

    def runnable(self, plan: ExecutionPlan) -> ExecutionPlan:
        """The plan as it runs: without the steps left unrun."""
        steps = [step for step in plan.steps if step.step_id not in self.not_run]
        return plan.model_copy(update={"steps": steps})

    def held_previous(self) -> dict[str, Any] | None:
        """What ``held_plan_of`` carries from this pass: the steps left unrun, said."""
        return {"not_run": self.not_run} if self.not_run else None


def plan_choice_of_turn(state: Any) -> dict[str, Any] | None:
    """This turn's plan-choice context, or None (a stale one never matches)."""
    context = state.get(STATE_KEY_PLAN_CHOICE)
    if isinstance(context, dict) and context.get("turn_id") == state.get(STATE_KEY_CURRENT_TURN_ID):
        return context
    return None


def pending_choice(state: Any) -> dict[str, Any] | None:
    """The question waiting for an answer in this turn, if any."""
    context = plan_choice_of_turn(state)
    pending = context.get("pending") if context else None
    return pending if isinstance(pending, dict) and not context.get("declined") else None


def answered_choice(context: dict[str, Any], index: int) -> dict[str, Any]:
    """The context once the person chose the ``index``-th option (1-based)."""
    pending = context["pending"]
    answered = {**(context.get("answered") or {}), pending["source"]: index}
    return {**context, "pending": None, "answered": answered}


def declined_choice(context: dict[str, Any], action: str) -> dict[str, Any]:
    """The context once the person declined to choose (« none of them », a refusal)."""
    return {**context, "pending": None, "declined": action}


def _acts(tool_name: str) -> bool:
    manifest, _ = resolve_tool_manifest_named(tool_name)
    return getattr(manifest, "mutation_policy", None) in ACTING_POLICIES


def _says_which(state: Any) -> bool:
    """Whether the request may give the item's position (« the latest », « the first »).

    It only keeps the planner's cap of one: « last » is also in « last week », a
    date that leaves several items open, so it never silences a question.
    """
    intelligence = state.get("query_intelligence")
    query = intelligence.get("original_query") if isinstance(intelligence, dict) else None
    if not isinstance(query, str) or not query:
        return False
    words = REQUEST_POSITION_WORDS[resolve_language(state.get("user_language"))]
    folded = fold_name(query)
    return any(token in words for token in answer_tokens(query)) or any(
        word in folded for word in words if not word.isascii()
    )


def _option_cap(tool_name: str) -> Any:
    """The options a widened lookup returns: the configured count, within the tool's bound."""
    manifest, _ = resolve_tool_manifest_named(tool_name)
    parameters = getattr(manifest, "parameters", None) or []
    schema = next((p for p in parameters if p.name == "max_results"), None)
    return clamp_to_parameter_schema(schema, settings.entity_resolution_max_candidates)


def _widened(plan: ExecutionPlan, points: list[ChoicePoint]) -> ExecutionPlan:
    """The plan its lookups run first from: a cap of one result raised to the options."""
    sources = {point.source_step_id for point in points}
    steps = [
        (
            step.model_copy(
                update={
                    "parameters": {
                        **step.parameters,
                        "max_results": _option_cap(step.tool_name or ""),
                    }
                }
            )
            if step.step_id in sources and (step.parameters or {}).get("max_results") in (1, "1")
            else step
        )
        for step in plan.steps
    ]
    return plan.model_copy(update={"steps": steps})


def _domain(list_path: str) -> str:
    return list_path.rsplit(".", 1)[-1]


def _narrowed(context: dict[str, Any], run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The lookups' results and registry, each answered list reduced to its chosen item.

    Built afresh from the stored snapshot on every pass, so a resumed round
    narrows the same lists once and only once.
    """
    completed: dict[str, Any] = copy.deepcopy(context.get("completed") or {})
    registry: dict[str, Any] = copy.deepcopy(context.get("registry") or {})
    paths: dict[str, str] = context.get("paths") or {}
    for source, index in (context.get("answered") or {}).items():
        originals = extract_value_by_path(completed.get(source) or {}, paths.get(source, ""))
        if not isinstance(originals, list) or not 1 <= index <= len(originals):
            continue
        chosen = originals[index - 1]
        replace_filtered_source_items(completed[source], paths[source], originals, [chosen])
        for unchosen in originals[: index - 1] + originals[index:]:
            registry.pop(_registry_id(paths[source], unchosen) or "", None)
        logger.info("plan_choice_narrowed", run_id=run_id, source=source, kept=index)
    return completed, registry


def _registry_id(list_path: str, item: object) -> str | None:
    """The registry id of one listed item — what its card is drawn from."""
    config = get_registry_config_for_items_key(_domain(list_path))
    key = item.get(config[1]) if config and isinstance(item, dict) else None
    if not config or not isinstance(key, str) or not key:
        return None
    return generate_registry_id(RegistryItemType(config[0]), key)


def _question(
    point: ChoicePoint, completed: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any] | None:
    """The pending question for a point whose lookup found several, else None."""
    if point.source_step_id in (context.get("answered") or {}):
        return None
    found = extract_value_by_path(completed.get(point.source_step_id) or {}, point.list_path)
    domain = _domain(point.list_path)
    if not isinstance(found, list) or len(found) < 2 or ContextTypeRegistry.find(domain) is None:
        return None
    # The answer's position indexes this very list: an item that is no record
    # could not be drawn as an option, and would shift every position after it.
    if not all(isinstance(item, dict) for item in found):
        return None
    return {
        "source": point.source_step_id,
        "act": point.act_step_id,
        "domain": domain,
        "candidates": found[: settings.entity_resolution_max_candidates],
    }


async def settle_plan_choice(
    plan: ExecutionPlan,
    state: Any,
    config: RunnableConfig,
    run_id: str,
    *,
    initial_registry: dict[str, Any] | None,
) -> ChoicePass:
    """Run the lookups an act takes the first result of, and ask when one found several.

    Args:
        plan: The plan about to run.
        state: The graph state.
        config: The run's config.
        run_id: The run.
        initial_registry: The registry the steps resolve references against.

    Returns:
        A pass whose ``ask`` hands off to the question, or the results the
        plan runs from (empty when the plan has no such act).
    """
    bound = _bound_to_designation(plan, state, run_id)
    plan = bound or plan
    context = plan_choice_of_turn(state)
    if context is None or context.get("plan_id") != plan.plan_id:
        context = await _first_pass(plan, state, config, run_id, initial_registry)
        if context is None:
            return ChoicePass(plan=bound)
    completed, registry = _narrowed(context, run_id)
    if context.get("declined"):
        not_run = _not_chosen(plan, context)
        logger.info("plan_choice_declined", run_id=run_id, not_run=len(not_run))
        return ChoicePass(completed=completed, registry=registry, not_run=not_run, plan=bound)
    pending = _next_question(context, completed)
    if pending is not None:
        logger.info("plan_choice_asked", run_id=run_id, candidates=len(pending["candidates"]))
        ask = {**context, "pending": pending}
        return ChoicePass(ask={STATE_KEY_PLAN_CHOICE: ask, STATE_KEY_EXECUTION_PLAN: plan})
    return ChoicePass(completed=completed, registry=registry, plan=bound)


def _bound_to_designation(plan: ExecutionPlan, state: Any, run_id: str) -> ExecutionPlan | None:
    """The plan acting on the item this turn designated, when it looked it up again."""
    resolved = state.get(STATE_KEY_RESOLVED_CONTEXT)
    if not isinstance(resolved, dict) or not resolved.get("items"):
        return None
    source_domain = str(resolved.get("source_domain") or "")
    domain = TOOL_PATTERN_TO_DOMAIN_MAP.get(source_domain, source_domain)
    bound = bind_designated_item(plan, list(resolved["items"]), domain, _acts)
    if bound is not None:
        logger.info("plan_bound_to_designated_item", run_id=run_id, domain=domain)
    return bound


def _not_chosen(plan: ExecutionPlan, context: dict[str, Any]) -> dict[str, str]:
    """The acts no item was chosen for, and every step depending on one of them."""
    answered = context.get("answered") or {}
    unchosen = {act for act, source, _ in context.get("points") or [] if source not in answered}
    graph = DependencyGraph(plan)
    return {
        step.step_id: NOT_CHOSEN
        for step in plan.steps
        if step.step_id in unchosen or unchosen & graph.get_all_dependencies(step.step_id)
    }


async def _first_pass(
    plan: ExecutionPlan,
    state: Any,
    config: RunnableConfig,
    run_id: str,
    initial_registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Run the lookups an act takes the first result of; None when none needs to."""
    if not settings.entity_resolution_enabled or not turn_follows_the_conversation():
        return None
    points = choice_points(plan, _acts)
    if not points:
        return None
    turn_id = state.get(STATE_KEY_CURRENT_TURN_ID)
    result = await execute_steps_first(
        plan if _says_which(state) else _widened(plan, points),
        {point.source_step_id for point in points},
        config,
        run_id,
        initial_registry=initial_registry,
        turn_id=turn_id,
    )
    if result is None:
        return None
    return {
        "plan_id": plan.plan_id,
        "turn_id": turn_id,
        "points": [[p.act_step_id, p.source_step_id, p.list_path] for p in points],
        "paths": {p.source_step_id: p.list_path for p in points},
        "completed": result.completed_steps,
        "registry": result.registry or {},
        "answered": {},
    }


def _next_question(context: dict[str, Any], completed: dict[str, Any]) -> dict[str, Any] | None:
    """The first point still unanswered whose lookup found several items."""
    for act, source, path in context.get("points") or []:
        pending = _question(ChoicePoint(act, source, path), completed, context)
        if pending is not None:
            return pending
    return None
