"""Person-360 overview tool (P3, ADR-141 — rebuilt on the CRM services).

One call aggregates everything the assistant knows about a person: the
database-local half the personal CRM already owns (open commitments, calls,
relayed messages), the provider-backed half (contact card, mail exchanged,
meetings shared), and the long-term memories that are ABOUT the person —
semantically, which is a different read from the page's literal name match.

**The assembly itself lives in ``domains/relations/overview``**, not here. It
used to, while this tool was its only consumer; the daily relationship debrief
needs the same answer, and a second implementation would let two surfaces
disagree about who someone is and what was read about them (ADR-185). What
remains here is the tool: resolve the caller, read their scope, and put the
assembled payload in the ONE field that reaches the response prompt.

The SCOPE is not inferred from the request. The chat link carries prose, so
the user's selection is written server-side before the chat opens and read
back here (``RelationOverviewScope``): what they ticked is what the assistant
gets, whatever the sentence says.

Each half keeps its own failure boundary — the overview is honestly PARTIAL
rather than all-or-nothing. Read-only, no HITL.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.domains.agents.constants import AGENT_CONTACT
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.sms.overview import overview_output
from src.domains.agents.tools.decorators import read_tool, with_user_preferences
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)
from src.domains.relations.overview import (
    OverviewEvidenceUnavailable,
    build_overview_evidence,
    overview_payload,
)
from src.domains.relations.service import RelationsService

logger = structlog.get_logger(__name__)


def _overview_message(payload: dict[str, Any]) -> str:
    """The overview's header: whose overview, and which blocks could not be read.

    The payload itself reaches the response model as the tool's data block, in
    both execution modes (ADR-347): ``compose_tool_message`` in ReAct, the
    step's projected record in the pipeline. Until then the pipeline read this
    message alone, so the payload was serialised HERE as compact JSON — measured
    2026-08-01, an assistant answering *"I have no data at hand"* over a payload
    stuck in ``structured_data`` — and the ReAct loop received it twice
    (median 460 tokens over the 18 golden cases, up to about 7 000 with every
    block full). The data block also wraps it as external content: relayed
    messages are third-party text.

    Args:
        payload: The overview payload, exactly as ``structured_data`` carries it.

    Returns:
        One line.
    """
    person = payload.get("person", "")
    unavailable = payload.get("unavailable") or []
    # The gap is stated in the HEADER, not left to be inferred from a key
    # buried in the payload: "could not read" and "read and found nothing" are
    # the distinction the whole design rests on (ADR-190), and it is the one a
    # model is most likely to flatten when it is not said plainly.
    gap = f" (could not read: {', '.join(unavailable)})" if unavailable else ""
    return f"360 overview for {person}{gap}."


@read_tool(name="get_person_overview", agent_name=AGENT_CONTACT)
@with_user_preferences
async def get_person_overview_tool(
    person_name: Annotated[
        str,
        "Person to build the 360 overview for: a relationship name as the user "
        "says it (Marie, Marie Dupont, or a nickname already resolved).",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    user_timezone: str = "UTC",
    locale: str | None = None,
) -> UnifiedToolOutput:
    """360° overview of ONE person, across the CRM and the connected accounts.

    Reads exactly what the user selected on the relationship card — the scope
    is stored server-side, never inferred from the request's wording.

    Args:
        person_name: Person to resolve and aggregate.
        runtime: LangChain tool runtime.
        user_timezone: Injected user timezone (preference contract).
        locale: Injected user language (preference contract).

    Returns:
        UnifiedToolOutput with the selected blocks plus ``unavailable`` —
        honestly partial rather than silently empty.
    """
    config = validate_runtime_config(runtime, "get_person_overview_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)

    scope = await RelationsService(user_id).get_overview_scope()
    try:
        evidence = await build_overview_evidence(user_id, person_name, scope)
    except OverviewEvidenceUnavailable:
        return UnifiedToolOutput.failure(
            message=f"could not read the relationship '{person_name}'",
            error_code="person_overview_unavailable",
        )

    payload = overview_payload(evidence)
    logger.info(
        "person_overview_built",
        user_id=str(user_id),
        blocks=sorted(evidence.blocks),
        unavailable=evidence.unavailable,
    )
    return overview_output(payload, evidence, user_id, _overview_message(payload))
