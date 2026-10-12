"""JEV names what a guarded value IS; the code decides whether the parameter accepts it.

ADR-325 usage ``parameter_kind``, measured as decision d5 of the 2026-10-11
qualification (``docs/technical/JEV_SEMANTIC_QUALIFICATION.md``): under this
module's rule the judged kind decided compatibility right on 58 of 66
independent cases, refusing no compatible value, where the deterministic
person-name rule decided 36. It runs only after that rule passed and can only
ADD a refusal: switched off, without an owner or a request, uncertain, failed
or refused by a quota, it refuses nothing and the call proceeds exactly as
before (ADR-120 amendment 2026-10-11).
"""

import asyncio
from collections.abc import Iterable, Mapping
from time import perf_counter
from typing import TYPE_CHECKING, Any

from pydantic import JsonValue

from src.core.constants import JEV_PARAMETER_KIND_MAX_VALUES, JEV_PARAMETER_KIND_MIN_CONFIDENCE
from src.core.context import current_tracker
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.semantic.param_guard import (
    GUARDED_SEMANTIC_TYPES,
    VALUE_KIND_LABELS,
    GuardedValue,
    SemanticParamViolation,
    guarded_values,
    proven_by_binding,
)
from src.domains.agents.semantic.value_bindings import BindingScope
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import JevSnapshot, load_jev_snapshot
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_many_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceQuestion
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext

logger = get_logger(__name__)

#: The kinds the judgment is offered, in the order the question lists them.
VALUE_KINDS: tuple[str, ...] = tuple(VALUE_KIND_LABELS)

#: The CODE's rule: which judged kinds each guarded semantic type accepts. A
#: location refuses only a value positively identified as something else: a
#: calendar's location is free text (« Visio », a room) that ``other`` names
#: without making it wrong, and no measured case said otherwise. An event's
#: location may be an online-meeting link — both calendar providers store one
#: there — so a physical address accepts a link. An email parameter accepts an
#: email address alone: nothing else can reach a mailbox.
_LOCATION = frozenset({"postal_address", "place", "other"})
ACCEPTED_VALUE_KINDS: dict[str, frozenset[str]] = {
    "physical_address": _LOCATION | {"link"},
    "locality": _LOCATION,
    "email_address": frozenset({"email_address"}),
}
if set(ACCEPTED_VALUE_KINDS) != set(GUARDED_SEMANTIC_TYPES) or not all(
    accepted <= set(VALUE_KINDS) for accepted in ACCEPTED_VALUE_KINDS.values()
):
    raise RuntimeError("Every guarded semantic type must declare the judged kinds it accepts")
_DECISION_LABELS = {"selection": "What a guarded tool argument is"}


def _decided_kind(attempt: DecisionAttempt) -> str | None:
    """The judged kind, or None when the judgment is absent or not confident enough."""
    answer = attempt.answer
    if (
        attempt.outcome != "success"
        or answer is None
        or answer.choice not in VALUE_KINDS
        or answer.confidence < JEV_PARAMETER_KIND_MIN_CONFIDENCE
    ):
        return None
    return answer.choice


def _values_to_judge(items: Iterable[GuardedValue], scope: BindingScope) -> list[GuardedValue]:
    """Each distinct value once, skipping what a selected canonical field already proves."""
    bindings, account, sources = scope
    seen: set[tuple[str, str, str]] = set()
    kept: list[GuardedValue] = []
    for item in items:
        key = (item.param.name, item.semantic_type, item.value)
        if key in seen or not item.value.strip():
            continue
        seen.add(key)
        if not proven_by_binding(item, bindings, account, sources):
            kept.append(item)
    return kept


def _state(item: GuardedValue, tool_name: str, request: str) -> dict[str, JsonValue]:
    """The measured D5 state: the request, the parameter as published, the value."""
    return {
        "query": request,
        "parameter": {
            "tool": tool_name,
            "name": item.param.name,
            "semantic_type": item.semantic_type,
            "description": item.param.description,
        },
        "value": item.value,
    }


async def _judge_value(
    item: GuardedValue,
    *,
    tool_name: str,
    request: str,
    question: ChoiceQuestion,
    snapshot: JevSnapshot,
    tracker: TrackingContext,
) -> SemanticParamViolation | None:
    """One value, one request; any failure leaves this value to the deterministic rule."""
    started = perf_counter()
    try:
        attempt = await choose_many_with_jev(
            usage=JevUsage.PARAMETER_KIND,
            user_id=tracker.user_id,
            run_id=tracker.run_id,
            state=_state(item, tool_name, request),
            questions={"selection": question},
            snapshot=snapshot,
        )
    except Exception as exc:  # noqa: BLE001 — an optional judgment never breaks a tool call
        logger.info("jev_parameter_kind_fallback", error_type=type(exc).__name__)
        return None
    kind = _decided_kind(attempt)
    refused = kind is not None and kind not in ACCEPTED_VALUE_KINDS[item.semantic_type]
    if attempt.outcome != "success":
        outcome = attempt.outcome
    else:
        outcome = "uncertain" if kind is None else ("refused" if refused else "accepted")
    await record_action(
        tracker.user_id,
        attempt.diagnostic,
        action="selected" if refused else ("observed" if kind else "fallback"),
        outcome=outcome,
        target="tool_call_refused" if refused else "tool_call",
        decision_labels=_DECISION_LABELS,
    )
    jev_decisions_total.labels(usage=JevUsage.PARAMETER_KIND, outcome=outcome).inc()
    jev_decision_duration_seconds.labels(usage=JevUsage.PARAMETER_KIND, outcome=outcome).observe(
        perf_counter() - started
    )
    if not refused:
        return None
    return SemanticParamViolation(
        tool_name=tool_name,
        param_name=item.path,
        semantic_type=item.semantic_type,
        value=item.value,
        value_kind=kind,
    )


def _turn_owner(request: str | None) -> tuple[TrackingContext, str] | None:
    """The turn's tracker and the person's words, when both exist.

    The tracker is the only owner: it supplies the account and the run the
    decision is billed to, so the cost lands on the turn's own summary.
    """
    tracker = current_tracker.get()
    if tracker is None or not tracker.run_id or not request or not request.strip():
        return None
    return tracker, request


async def _prepared(
    tool_name: str, args: Mapping[str, Any], scope: BindingScope
) -> tuple[list[GuardedValue], JevSnapshot, ChoiceQuestion] | None:
    """The values to judge, the switch snapshot and the question — or None to judge nothing."""
    manifest = available_manifest(tool_name)
    if manifest is None:
        return None
    items = _values_to_judge(guarded_values(manifest, args), scope)
    if not items:
        return None
    if len(items) > JEV_PARAMETER_KIND_MAX_VALUES:
        logger.debug("jev_parameter_kind_values_capped", tool_name=tool_name, values=len(items))
        items = items[:JEV_PARAMETER_KIND_MAX_VALUES]
    snapshot = await load_jev_snapshot(JevUsage.PARAMETER_KIND)
    if not snapshot.requested:
        return None
    question = ChoiceQuestion.model_validate_json(
        load_prompt("jev_parameter_kind_question", version="v1")
    )
    return items, snapshot, question


async def judge_guarded_values(
    tool_name: str,
    args: Mapping[str, Any],
    *,
    request: str | None,
    scope: BindingScope | None = None,
) -> SemanticParamViolation | None:
    """Refuse a guarded value JEV confidently judges to be of a kind its parameter refuses.

    Args:
        tool_name: Tool about to be executed.
        args: Final arguments (after Jinja2 / $steps resolution).
        request: The person's words for the turn.
        scope: The binding evidence; a value it proves is not judged.

    Returns:
        The first refused value in manifest order, or None.
    """
    owner = _turn_owner(request)
    if owner is None or not args:
        return None
    tracker, words = owner
    try:
        prepared = await _prepared(tool_name, args, scope or ((), None, {}))
    except Exception as exc:  # noqa: BLE001 — fail-open, like the deterministic guard
        logger.debug("jev_parameter_kind_failed_open", error_type=type(exc).__name__)
        return None
    if prepared is None:
        return None
    items, snapshot, question = prepared
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(
                _judge_value(
                    item,
                    tool_name=tool_name,
                    request=words,
                    question=question,
                    snapshot=snapshot,
                    tracker=tracker,
                )
            )
            for item in items
        ]
    return next((task.result() for task in tasks if task.result() is not None), None)
