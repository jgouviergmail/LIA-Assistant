"""A sandbox run's network branch, from declared hosts to a plan (ADR-298, ADR-327 lot 3).

Kept out of the tools so each stays the small thing it is: this is where the
refusals of a network run are named and shaped for the model, and where the
person is asked about an unknown host. Two tools share it — the ephemeral
Python script and a skill's command — so a host is permitted by the same rule
whichever one declares it.

The question is settled IN the ReAct loop (``nodes/react_egress_question``):
the person's answer is handed to the very call that asked, re-invoked, through
:func:`approved_for_call` — a context the node opens around that one
invocation, so the approval never outlives it and never reaches another call.
Anywhere else — a skill's isolated runner, a plan step, a loop nested under
the call — nobody can settle the question, so an unknown host is refused with
where the person allows it (``egress/settlement`` marks the calls that can ask).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Final

import structlog

from src.core.config import get_settings
from src.core.constants import PYTHON_SANDBOX_TOOL_NAME
from src.core.i18n import resolve_language
from src.domains.agents.python_sandbox.egress.grants import load_grants, mark_relied_grants
from src.domains.agents.python_sandbox.egress.hosts import (
    HostDecision,
    InvalidHost,
    normalize_hosts,
)
from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.domains.agents.python_sandbox.egress.run import (
    NetworkRunPlan,
    decide_hosts,
    execute_network_run,
    plan_network_run,
)
from src.domains.agents.python_sandbox.egress.settlement import (
    question_settleable,
    settling_questions,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.skills.executor import ScriptResult
from src.infrastructure.observability.metrics_react import python_sandbox_egress_runs_total

logger = structlog.get_logger(__name__)

#: ``{host: share_turn_data}`` the person just answered for THIS invocation
#: (one-shot at the cap, or not yet re-read from the table). Read beside the
#: stored grants; set only by ``approved_for_call``.
_approved_hosts: ContextVar[Mapping[str, bool] | None] = ContextVar(
    "python_sandbox_approved_hosts", default=None
)


def approved_hosts() -> Mapping[str, bool]:
    """What the person allowed for the invocation in progress, if anything."""
    return _approved_hosts.get() or {}


@contextmanager
def approved_for_call(hosts: Mapping[str, bool]) -> Iterator[None]:
    """Hand an answer to the next invocation of the tool, and to it alone.

    Args:
        hosts: ``{host: share_turn_data}`` — the card's hosts and the scope
            the person chose.
    """
    token = _approved_hosts.set(dict(hosts))
    try:
        yield
    finally:
        _approved_hosts.reset(token)


#: Outcomes of the counters — each a distinct thing an operator acts on.
OUTCOME_ALLOWED: Final = "allowed"
OUTCOME_ASKED: Final = "asked"
OUTCOME_REFUSED: Final = "refused"
OUTCOME_PROXY_UNAVAILABLE: Final = "proxy_unavailable"


@dataclass(frozen=True)
class NetworkRefusal:
    """A network run that will not start, as the tool returns it.

    Attributes:
        output: What the model reads — a refusal, or the egress question.
        outcome: The counter's label (``refused``, ``asked``).
    """

    output: UnifiedToolOutput
    outcome: str


def _refusal(message: str, code: ToolErrorCode) -> NetworkRefusal:
    return NetworkRefusal(
        UnifiedToolOutput(success=False, message=message, error_code=code), OUTCOME_REFUSED
    )


async def authorize_network(
    raw_hosts: list[str],
    *,
    context: Any,
    purpose: str,
    items: Mapping[str, Any],
    tool_name: str,
    third_party_skill: bool = False,
) -> NetworkRunPlan | NetworkRefusal:
    """Validate, classify, ask or refuse — the plan of a permitted network run.

    Args:
        raw_hosts: What the model declared.
        context: The typed runtime context (user id, dependency container, language).
        purpose: What the run is for — the card shows it.
        items: What the run would carry of the turn — counted on the card by
            kind, never carried in it.
        tool_name: The tool asking, named on the card and in the logs.
        third_party_skill: Whether a skill written elsewhere asks (ADR-327):
            the person's connector hosts and their tokens are then withheld,
            and the card says who asks.

    Returns:
        The plan, or the refusal (or question) the tool returns as is.
    """
    settings = get_settings()
    # The deployment ceiling AND the operator's switch, read at the act
    # (ADR-280): flipping it must take effect without a restart.
    from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled

    if not await is_capability_enabled(PlatformCapability.PYTHON_SANDBOX_EGRESS):
        return _refusal(
            "Network runs are disabled on this instance: declare no hosts.",
            ToolErrorCode.CONFIGURATION_ERROR,
        )
    try:
        hosts = normalize_hosts(raw_hosts, cap=settings.python_sandbox_max_hosts_per_run)
    except InvalidHost as exc:
        return _refusal(
            f"Invalid hosts: {exc}. Declare bare lowercase hostnames only.",
            ToolErrorCode.INVALID_INPUT,
        )
    user_id = context.user_id
    gate = await context.deps.get_connector_service()
    # What the person just allowed for THIS invocation joins the stored grants
    # — remembered or not (one-shot at the cap), the answer holds for the run.
    grants = {**await load_grants(user_id), **approved_hosts()}
    decision = await decide_hosts(
        hosts, user_id=user_id, gate=gate, grants=grants, with_connectors=not third_party_skill
    )
    if decision.unknown:
        return _unknown_hosts(
            decision,
            ask_enabled=settings.python_sandbox_egress_ask_enabled,
            purpose=purpose,
            items=items,
            tool_name=tool_name,
            language=resolve_language(getattr(context, "language", None)),
            third_party_skill=third_party_skill,
        )
    return await plan_network_run(
        decision, run_id=uuid.uuid4().hex[:16], user_id=user_id, gate=gate
    )


def _unknown_hosts(
    decision: HostDecision,
    *,
    ask_enabled: bool,
    purpose: str,
    items: Mapping[str, Any],
    tool_name: str,
    language: str,
    third_party_skill: bool,
) -> NetworkRefusal:
    """What happens to a host nobody permitted: asked, or refused."""
    listed = ", ".join(decision.unknown)
    if not ask_enabled:
        return _refusal(
            f"Hosts not permitted on this instance: {listed}. "
            "Declare only hosts the person's connectors or the operator allow.",
            ToolErrorCode.FORBIDDEN,
        )
    if not question_settleable():
        return _refusal(
            f"Hosts not permitted yet: {listed}. Nobody can be asked from here: tell the "
            "person they can allow these hosts in Settings (network access of scripts and "
            "skill commands), then run it again. Do not retry without them.",
            ToolErrorCode.FORBIDDEN,
        )
    from src.domains.agents.python_sandbox.egress.draft import ask_for_hosts

    return NetworkRefusal(
        ask_for_hosts(
            decision=decision,
            purpose=purpose,
            items=items,
            language=language,
            tool_name=tool_name,
            third_party_skill=third_party_skill,
        ),
        OUTCOME_ASKED,
    )


async def run_with_network(
    raw_hosts: list[str], *, code: str, purpose: str, context: Any, items: dict[str, Any]
) -> UnifiedToolOutput | tuple[ScriptResult, dict[str, Any]]:
    """The ephemeral script's network run: authorize, then run on the sandbox network.

    Args:
        raw_hosts: What the model declared.
        code: The script.
        purpose: What the model said it computes — the card shows it.
        context: The typed runtime context (user id, dependency container).
        items: The turn's collected data, handed over only when the decision
            allows it.

    Returns:
        A refusal the tool returns as is, or the script's result with the
        ``structured_data`` fields a network run adds.
    """
    plan = await authorize_network(
        raw_hosts,
        context=context,
        purpose=purpose,
        items=items,
        tool_name=PYTHON_SANDBOX_TOOL_NAME,
    )
    if isinstance(plan, NetworkRefusal):
        python_sandbox_egress_runs_total.labels(outcome=plan.outcome).inc()
        return plan.output
    user_id = context.user_id
    payload = {"items": items if plan.share_turn_data else {}}
    try:
        result = await execute_network_run(plan, source=code, payload=payload, user_id=user_id)
    except EgressProxyUnavailable as exc:
        logger.warning("sandbox_egress_run_refused", reason=str(exc), user_id=str(user_id))
        python_sandbox_egress_runs_total.labels(outcome=OUTCOME_PROXY_UNAVAILABLE).inc()
        return UnifiedToolOutput(
            success=False,
            message=(
                f"Egress proxy unavailable: {exc}. The run did not start; "
                "answer with what you have."
            ),
            error_code=ToolErrorCode.CONFIGURATION_ERROR,
        )
    python_sandbox_egress_runs_total.labels(outcome=OUTCOME_ALLOWED).inc()
    await mark_relied_grants(user_id, plan.statuses)
    return result, network_fields(plan)


def network_fields(plan: NetworkRunPlan) -> dict[str, Any]:
    """What a network run adds to the tool's ``structured_data`` — both tools alike."""
    return {
        "hosts": list(plan.run.hosts),
        "turn_data_shared": plan.share_turn_data,
        "authorizations": {host: status.value for host, status in plan.statuses.items()},
    }


__all__ = [
    "OUTCOME_ALLOWED",
    "OUTCOME_ASKED",
    "OUTCOME_PROXY_UNAVAILABLE",
    "OUTCOME_REFUSED",
    "NetworkRefusal",
    "approved_for_call",
    "approved_hosts",
    "authorize_network",
    "network_fields",
    "question_settleable",
    "run_with_network",
    "settling_questions",
]
