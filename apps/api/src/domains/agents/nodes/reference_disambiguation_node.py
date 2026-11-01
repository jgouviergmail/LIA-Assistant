"""« Which of the items shown did you mean? » — asked before anything is planned (ADR-367).

The person designated an item by WHAT it is (« reply to Marc's email ») and
several of the items the last answers SHOWED fit those words: the resolver left
them as CANDIDATES (``descriptive_reference.py``). Choosing one ourselves is
how the incident of 2026-10-29 happened — a reply drafted to an e-mail the
person had never seen — so this node asks, between the router and the planner,
in both execution modes:

- the question is a template (``EntityDisambiguationInteraction``): numbered
  options, each telling itself apart (sender, subject, date), and how to
  answer — no model is called, here or to read the answer;
- a choice becomes the turn's ONE resolved item, exactly as if the person had
  named it alone; « none of them » plans a new lookup, the path every request
  took before; a refusal ends the turn with nothing done;
- an answer naming no single option is asked about ONCE more — never guessed;
  typed a second time, it is the person's new request: the question is dropped
  and the words run as a turn of their own (``approval_decision``), never lost.
  Only a malformed click left unclear twice cancels here.

The same question is asked when a plan would act on the first of several items
a lookup FOUND (``nodes/plan_choice.py``): the chosen one is what the plan then
acts on; after « none of them » or a refusal the plan runs without that act.

Replay-safe: LangGraph re-runs this node from the top on every resume and the
answers come back in order, so nothing between the two questions may differ
from one run to the next — nothing here calls a model, reads the clock or
touches a store.
"""

from __future__ import annotations

from typing import Any, Final

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.core.i18n import resolve_language
from src.domains.agents.analysis.query_intelligence_helpers import STATE_KEY_QUERY_INTELLIGENCE
from src.domains.agents.constants import (
    NODE_REFERENCE_DISAMBIGUATION,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_CHOICE,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_RESOLVED_CONTEXT,
    STATE_KEY_TURN_TYPE,
)
from src.domains.agents.context.choice_answer import (
    CHOICE_NONE,
    CHOICE_SELECT,
    CHOICE_UNCLEAR,
    ChoiceAnswer,
)
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.plan_choice import (
    answered_choice,
    declined_choice,
    pending_choice,
    plan_choice_of_turn,
)
from src.domains.agents.services.analysis.query_context import determine_turn_type
from src.domains.agents.services.descriptive_reference import candidate_label
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.services.reference_resolver import ResolvedContext
from src.domains.agents.utils.turn_type import normalize_turn_type
from src.domains.agents.utils.type_domain_mapping import TOOL_PATTERN_TO_DOMAIN_MAP
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
    context_disambiguation_answers_total,
)

logger = get_logger(__name__)

__all__ = ["CHOICE_DECLINED_REASON", "asks_which_item", "reference_disambiguation_node"]

#: Why the turn ended with nothing done — read by the response's rejection
#: directive, model-facing technical English like every rejection reason.
CHOICE_DECLINED_REASON: Final = "The user did not choose which of the items shown they meant"


def asks_which_item(state: MessagesState) -> bool:
    """Whether the turn must first ask which shown item the person meant.

    Args:
        state: The graph state, the router's resolution in it.

    Returns:
        True when a description fits several shown items and none was resolved.
    """
    context = state.get(STATE_KEY_RESOLVED_CONTEXT)
    shown = (
        isinstance(context, dict) and bool(context.get("candidates")) and not context.get("items")
    )
    return shown or pending_choice(state) is not None


def _definition(context: ResolvedContext) -> ContextTypeDefinition | None:
    domain = context.source_domain or ""
    return ContextTypeRegistry.find(TOOL_PATTERN_TO_DOMAIN_MAP.get(domain, domain))


def _question(context: ResolvedContext, definition: ContextTypeDefinition) -> dict[str, Any]:
    """The action request the question is drawn from (and the card's options)."""
    return {
        "type": HitlInteractionType.ENTITY_DISAMBIGUATION.value,
        "domain": context.source_domain,
        "descriptor": context.descriptor,
        "candidates": [
            {"index": index, "label": candidate_label(payload, definition)}
            for index, payload in enumerate(context.candidates, 1)
        ],
    }


def _ask(request: dict[str, Any], language: str, *, reask: bool) -> ChoiceAnswer:
    answer = interrupt(
        {
            "action_requests": [{**request, "reask": reask}],
            "generate_question_streaming": True,
            "user_language": language,
            "hitl_type": HitlInteractionType.ENTITY_DISAMBIGUATION.value,
        }
    )
    return ChoiceAnswer.from_resume(answer, options=len(request["candidates"]))


def _answer(request: dict[str, Any], language: str) -> ChoiceAnswer:
    """Ask, once more when the answer named no option, and count how it ended."""
    answer = _ask(request, language, reask=False)
    asked_twice = answer.action == CHOICE_UNCLEAR
    if asked_twice:
        answer = _ask(request, language, reask=True)
    # select | none | cancel, « _after_reask » when asked twice, unclear: gave up.
    outcome = answer.action
    if asked_twice and outcome != CHOICE_UNCLEAR:
        outcome = f"{outcome}_after_reask"
    context_disambiguation_answers_total.labels(outcome=outcome).inc()
    logger.info(
        "reference_disambiguation_answered",
        outcome=outcome,
        asked_twice=asked_twice,
        candidates_count=len(request["candidates"]),
        found=bool(request.get("found")),
    )
    return answer


def _which_found(state: MessagesState, pending: dict[str, Any]) -> dict[str, Any]:
    """Ask which of the items a plan's lookup found it should act on."""
    context = plan_choice_of_turn(state) or {}
    definition = ContextTypeRegistry.find(str(pending.get("domain") or ""))
    candidates = pending.get("candidates") or []
    request = {
        "type": HitlInteractionType.ENTITY_DISAMBIGUATION.value,
        "domain": pending.get("domain"),
        "descriptor": "",
        "found": True,
        "candidates": [
            {"index": index, "label": candidate_label(payload, definition) if definition else ""}
            for index, payload in enumerate(candidates, 1)
        ],
    }
    answer = _answer(request, resolve_language(state.get("user_language")))
    if answer.action == CHOICE_SELECT and answer.index is not None:
        return {STATE_KEY_PLAN_CHOICE: answered_choice(context, answer.index)}
    # The lookup ran: the plan resumes without the act — never « nothing was read ».
    return {STATE_KEY_PLAN_CHOICE: declined_choice(context, answer.action)}


def _chosen(state: MessagesState, context: ResolvedContext, index: int) -> dict[str, Any]:
    """The turn as if the person had named the chosen item alone."""
    chosen = ResolvedContext(
        items=[context.candidates[index - 1]],
        confidence=1.0,
        method="descriptive_chosen",
        source_turn_id=None,
        source_domain=context.source_domain,
    )
    intelligence = state.get(STATE_KEY_QUERY_INTELLIGENCE)
    intent = intelligence.get("immediate_intent", "") if isinstance(intelligence, dict) else ""
    turn_type = determine_turn_type(chosen, str(intent or ""))
    update: dict[str, Any] = {
        STATE_KEY_RESOLVED_CONTEXT: chosen.to_dict(),
        STATE_KEY_TURN_TYPE: normalize_turn_type(turn_type),
    }
    if isinstance(intelligence, dict):
        update[STATE_KEY_QUERY_INTELLIGENCE] = {**intelligence, "turn_type": turn_type}
    return update


@track_metrics(
    node_name=NODE_REFERENCE_DISAMBIGUATION,
    duration_metric=agent_node_duration_seconds,
    counter_metric=agent_node_executions_total,
    log_execution=True,
    log_errors=True,
)
async def reference_disambiguation_node(
    state: MessagesState, config: RunnableConfig
) -> dict[str, Any]:
    """Ask which of the shown items fitting the person's words they meant.

    Also asks which of the items a plan's lookup found it should act on.

    Args:
        state: The graph state carrying the router's candidates.
        config: LangGraph configuration.

    Returns:
        The chosen item as the turn's resolution; no resolution for « none of
        them » (a new lookup); the plan-rejection state for a refusal. For a
        plan's choice, the answered (or declined) choice context.
    """
    if (pending := pending_choice(state)) is not None:
        return _which_found(state, pending)
    if not asks_which_item(state):
        return {}
    context = ResolvedContext.from_dict(state[STATE_KEY_RESOLVED_CONTEXT])
    definition = _definition(context)
    if definition is None:
        # The candidates came from a registered type; an unknown one cannot be
        # described, so it is looked up anew rather than asked about blindly.
        logger.warning("reference_disambiguation_unknown_domain")
        return {STATE_KEY_RESOLVED_CONTEXT: None}
    answer = _answer(_question(context, definition), resolve_language(state.get("user_language")))
    if answer.action == CHOICE_SELECT and answer.index is not None:
        return _chosen(state, context, answer.index)
    if answer.action == CHOICE_NONE:
        return {STATE_KEY_RESOLVED_CONTEXT: None}
    return {
        STATE_KEY_RESOLVED_CONTEXT: None,
        STATE_KEY_PLAN_APPROVED: False,
        STATE_KEY_PLAN_REJECTION_REASON: CHOICE_DECLINED_REASON,
    }
