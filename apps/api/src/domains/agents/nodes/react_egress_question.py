"""Settling the egress question INSIDE the ReAct loop (ADR-298).

A sandbox script that declares a host nobody permitted comes back from the
tool as a draft — the card the person answers with three buttons. Handing
that draft to the draft dispatch (the path every mutation draft takes) was
measured wrong on 2026-09-18: the dispatch EXECUTES a draft and answers from
its result, it never resumes the loop, so a question asked mid-plan (« count
the attachments of my last mails, and check httpbin.org ») ended the turn on
the httpbin result alone, the mails never counted.

A permission is not an action: it is asked, answered, and the SAME call goes
on. So the node raises the interrupt itself, exactly like a mutation tool's
pre-execution confirmation (``react_execute_tools_node``), with the payload
shape the draft-critique interaction already streams (card, question, three
answers); on resume the node re-runs, ``interrupt()`` hands the answer back,
the grant is recorded, and the call is re-invoked with the answer bound to
that one invocation (``tool_path.approved_for_call``). Nothing of the script
or the person's data ever travels in the card or the wire: the call still
holds its own arguments.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import structlog
from langgraph.types import interrupt

from src.core.constants import PYTHON_SANDBOX_TOOL_NAME
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.effects.scope import approved_scope, current_scope, effect_scope
from src.domains.agents.nodes.react_drafts import extract_draft_info
from src.domains.agents.python_sandbox.egress.grants import Decision, record_decision
from src.domains.agents.python_sandbox.egress.tool_path import approved_for_call
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.observability.metrics_react import (
    python_sandbox_egress_grants_total,
    react_agent_hitl_interrupts_total,
)

logger = structlog.get_logger(__name__)

#: The counter's label for an answer nobody stored (the cap) or a refusal.
DECISION_ONE_SHOT = "one_shot"
DECISION_REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class EgressAnswer:
    """What the person answered, read off the resume value.

    Attributes:
        allowed: True on an explicit confirmation only.
        share_turn_data: The scope chosen — meaningless when refused.
    """

    allowed: bool
    share_turn_data: bool


def is_egress_question(draft_info: Mapping[str, Any] | None) -> bool:
    """Is this draft the egress question, to be settled here rather than dispatched?"""
    return bool(draft_info) and draft_info.get("draft_type") == DraftType.SANDBOX_EGRESS.value


def build_interrupt_payload(draft_info: Mapping[str, Any], *, user_language: str) -> dict[str, Any]:
    """The interrupt value, in the shape ``hitl_dispatch`` raises for a draft.

    The streaming side keys on ``hitl_type`` to draw the card and its three
    answers through the draft-critique interaction; it never reads the state,
    so a draft raised from this node is drawn exactly like a dispatched one.
    """
    return {
        "action_requests": [
            {
                "type": "draft_critique",
                "draft_id": draft_info["draft_id"],
                "draft_type": draft_info["draft_type"],
                "draft_content": draft_info["draft_content"],
                "registry_ids": list(draft_info.get("registry_ids") or []),
                "tool_name": draft_info.get("tool_name") or PYTHON_SANDBOX_TOOL_NAME,
                "step_id": draft_info.get("step_id"),
            }
        ],
        "generate_question_streaming": True,
        "user_language": user_language,
        "hitl_type": HitlInteractionType.DRAFT_CRITIQUE.value,
    }


def read_answer(decision: Any) -> EgressAnswer:
    """A confirmation, and only a confirmation, is a yes.

    ``confirm_without_data`` reaches here canonised to ``confirm`` with
    ``share_turn_data: False`` beside it (``approval_decision``); anything
    else — cancel, edit, a malformed resume — is the safe answer.
    """
    action = decision.get("action") if isinstance(decision, Mapping) else None
    if action not in ("confirm", "approve"):
        return EgressAnswer(allowed=False, share_turn_data=False)
    return EgressAnswer(allowed=True, share_turn_data=bool(decision.get("share_turn_data", True)))


async def settle_egress_question(
    draft_info: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    rerun: Callable[[], Awaitable[Any]],
) -> Any:
    """Ask, record, and re-invoke the call under the answer — or refuse.

    Args:
        draft_info: The draft the tool returned (``_extract_draft_info``).
        state: The graph state, for the person's language.
        rerun: Re-invokes the very tool call; awaited only on a yes.

    Returns:
        The re-invocation's result, or a refusal the model can read.
    """
    payload = build_interrupt_payload(
        draft_info, user_language=str(state.get("user_language", "fr"))
    )
    # Halts the node on the first pass; hands the resume value back on the
    # re-execution (index-based, like the mutation interrupt beside it).
    answer = read_answer(interrupt(payload))
    hosts = [str(h) for h in draft_info["draft_content"].get("hosts_unknown") or []]
    context = runtime_context_if_running()
    user_id = getattr(context, "user_id", None)
    if not answer.allowed or user_id is None:
        python_sandbox_egress_grants_total.labels(decision=DECISION_REFUSED).inc()
        react_agent_hitl_interrupts_total.labels(
            tool_name=PYTHON_SANDBOX_TOOL_NAME, decision="reject"
        ).inc()
        logger.info(
            "sandbox_egress_question_refused", hosts=len(hosts), had_owner=user_id is not None
        )
        return UnifiedToolOutput(
            success=False,
            message=(
                f"The person refused network access to: {', '.join(hosts)}. "
                "Answer with what you have; do not declare these hosts again this turn."
            ),
            error_code=ToolErrorCode.FORBIDDEN,
        )
    decision = Decision.WITH_DATA if answer.share_turn_data else Decision.WITHOUT_DATA
    outcome = await record_decision(user_id, hosts, decision)
    python_sandbox_egress_grants_total.labels(
        decision=DECISION_ONE_SHOT if outcome.one_shot else decision.value
    ).inc()
    react_agent_hitl_interrupts_total.labels(
        tool_name=PYTHON_SANDBOX_TOOL_NAME, decision="approve"
    ).inc()
    logger.info(
        "sandbox_egress_question_answered",
        hosts=len(hosts),
        share_turn_data=outcome.share_turn_data,
        one_shot=outcome.one_shot,
    )
    # The answer holds for THIS invocation — remembered or not (one-shot at
    # the cap) — and for nothing that runs after it.
    with approved_for_call(dict.fromkeys(hosts, outcome.share_turn_data)):
        return await rerun()


async def invoke_with_settlement(
    wrapper: Any,
    injected_args: Mapping[str, Any],
    *,
    timeout: float,
    state: Mapping[str, Any],
    tool_name: str,
) -> Any:
    """Invoke one tool call and, if it asked the egress question, settle it.

    The node's one door to a tool's coroutine: any other draft comes back
    untouched for the dispatch, the egress question is asked here and the
    call re-invoked under the answer — inside the SAME effect scope, derived
    as approved by the card, so the network act's row names who approved it.

    Args:
        wrapper: The ReAct wrapper holding the original tool.
        injected_args: The call's arguments, runtime injected.
        timeout: The call's bound, applied to each invocation.
        state: The graph state.
        tool_name: The call's tool name.

    Returns:
        The tool's result, or the settled re-invocation's.
    """

    async def _call() -> Any:
        return await asyncio.wait_for(wrapper._original_tool.coroutine(**injected_args), timeout)

    raw_result = await _call()
    draft_info = extract_draft_info(raw_result, tool_name)
    if not is_egress_question(draft_info):
        return raw_result
    assert draft_info is not None  # narrowed by is_egress_question

    async def _rerun() -> Any:
        scope = current_scope()
        if scope is None:
            return await _call()
        with effect_scope(
            approved_scope(scope, kind="draft_critique", ref=str(draft_info["draft_id"]))
        ):
            return await _call()

    return await settle_egress_question(draft_info, state=state, rerun=_rerun)


__all__ = [
    "EgressAnswer",
    "build_interrupt_payload",
    "invoke_with_settlement",
    "is_egress_question",
    "read_answer",
    "settle_egress_question",
]
