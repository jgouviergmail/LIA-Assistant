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

import json
from typing import Annotated, Any

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.domains.agents.constants import AGENT_CONTACT
from src.domains.agents.context.runtime_context import LiaRuntimeContext
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
    """The overview, in the field the response synthesizer actually reads.

    Measured on the dev API, 2026-08-01: the tool ran, produced relayed
    messages, commitments and memories — and the assistant answered *"I have no
    data at hand"*. Its payload had reached ``structured_data`` and stopped
    there. Only two channels reach the response prompt: the **data registry**,
    fed exclusively by tools declaring a ``context_key``, and this ``message``
    field (``formatters/agent_results._extract_action_success_messages``). This
    tool has no ``context_key`` — deliberately: the registry serialises ITEMS
    for filtering, one truncated line each, which is the wrong shape for one
    person's briefing across nine heterogeneous blocks. So the message carried
    ``"overview built for X"``: proof the tool ran, and not one fact.

    Serialised as compact JSON, like the planner catalogue: lossless, and it
    preserves the distinction the whole design rests on — a block that could
    not be read carries NO key and is named in ``unavailable``, while an empty
    list means "looked, found nothing" (ADR-190).

    Args:
        payload: The overview payload, exactly as ``structured_data`` carries it.

    Returns:
        A one-line header plus the payload as compact JSON.
    """
    person = payload.get("person", "")
    unavailable = payload.get("unavailable") or []
    # The gap is stated in the HEADER, not left to be inferred from a key
    # buried in the payload: "could not read" and "read and found nothing" are
    # the distinction the whole design rests on (ADR-190), and it is the one a
    # model is most likely to flatten when it is not said plainly.
    gap = f" (could not read: {', '.join(unavailable)})" if unavailable else ""
    return f"360 overview for {person}{gap}:\n" + json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False, default=str
    )


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
    locale: str = "fr",
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
    return UnifiedToolOutput.data_success(
        message=_overview_message(payload),
        structured_data=payload,
    )
