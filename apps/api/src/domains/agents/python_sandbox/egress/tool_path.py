"""The tool's network branch, from declared hosts to a result (ADR-298).

Kept out of ``python_sandbox_tools`` so the tool module stays the small
thing it is: this is where the refusals of a network run are named, counted
and shaped for the model, and where the person is asked about an unknown
host.

The question is settled IN the loop (``nodes/react_egress_question``): the
person's answer is handed to the very call that asked, re-invoked, through
:func:`approved_for_call` — a context the node opens around that one
invocation, so the approval never outlives it and never reaches another call.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import structlog

from src.core.config import get_settings
from src.domains.agents.python_sandbox.egress.grants import load_grants, mark_relied_grants
from src.domains.agents.python_sandbox.egress.hosts import (
    HostDecision,
    InvalidHost,
    normalize_hosts,
)
from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.domains.agents.python_sandbox.egress.run import (
    decide_hosts,
    execute_network_run,
    plan_network_run,
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


#: Outcomes of the counter — each a distinct thing an operator acts on.
OUTCOME_ALLOWED = "allowed"
OUTCOME_ASKED = "asked"
OUTCOME_REFUSED = "refused"
OUTCOME_PROXY_UNAVAILABLE = "proxy_unavailable"


def _refusal(
    message: str, code: ToolErrorCode, outcome: str = OUTCOME_REFUSED
) -> UnifiedToolOutput:
    python_sandbox_egress_runs_total.labels(outcome=outcome).inc()
    return UnifiedToolOutput(success=False, message=message, error_code=code)


async def run_with_network(
    raw_hosts: list[str], *, code: str, purpose: str, context: Any, items: dict[str, Any]
) -> UnifiedToolOutput | tuple[ScriptResult, dict[str, Any]]:
    """Validate, classify, ask or refuse, then run on the sandbox network.

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
    decision = await decide_hosts(hosts, user_id=user_id, gate=gate, grants=grants)
    if decision.unknown:
        return _unknown_hosts(
            decision,
            ask_enabled=settings.python_sandbox_egress_ask_enabled,
            code=code,
            purpose=purpose,
            items=items,
            language=str(getattr(context, "language", "") or "en"),
        )
    run_id = uuid.uuid4().hex[:16]
    plan = await plan_network_run(decision, run_id=run_id, user_id=user_id, gate=gate)
    payload = {"items": items if plan.share_turn_data else {}}
    try:
        result = await execute_network_run(plan, source=code, payload=payload, user_id=user_id)
    except EgressProxyUnavailable as exc:
        logger.warning("sandbox_egress_run_refused", reason=str(exc), user_id=str(user_id))
        return _refusal(
            f"Egress proxy unavailable: {exc}. The run did not start; answer with what you have.",
            ToolErrorCode.CONFIGURATION_ERROR,
            OUTCOME_PROXY_UNAVAILABLE,
        )
    python_sandbox_egress_runs_total.labels(outcome=OUTCOME_ALLOWED).inc()
    await mark_relied_grants(user_id, plan.statuses)
    return result, {
        "hosts": list(plan.run.hosts),
        "turn_data_shared": plan.share_turn_data,
        "authorizations": {host: status.value for host, status in plan.statuses.items()},
    }


def _unknown_hosts(
    decision: HostDecision,
    *,
    ask_enabled: bool,
    code: str,
    purpose: str,
    items: dict[str, Any],
    language: str,
) -> UnifiedToolOutput:
    """What happens to a host nobody permitted: asked, or refused (strict policy)."""
    if not ask_enabled:
        return _refusal(
            f"Hosts not permitted on this instance: {', '.join(decision.unknown)}. "
            "Declare only hosts the person's connectors or the operator allow.",
            ToolErrorCode.FORBIDDEN,
        )
    from src.domains.agents.python_sandbox.egress.draft import ask_for_hosts

    python_sandbox_egress_runs_total.labels(outcome=OUTCOME_ASKED).inc()
    return ask_for_hosts(decision=decision, purpose=purpose, items=items, language=language)


__all__ = [
    "OUTCOME_ALLOWED",
    "OUTCOME_ASKED",
    "OUTCOME_PROXY_UNAVAILABLE",
    "OUTCOME_REFUSED",
    "approved_for_call",
    "approved_hosts",
    "run_with_network",
]
