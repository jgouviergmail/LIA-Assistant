"""Read the three CRM blocks the assistant had no capability for.

Until now the only door to calls, open commitments and relayed messages was
``get_person_overview_tool``, which lives in the ``contact`` domain. A question
about a call routes to ``telephony`` — whose entire catalogue was ONE tool:
place a phone call. Since the planner is told to cover its primary domain,
covering ``telephony`` meant WRITING: "de quand date mon dernier appel à ma
femme ?" was planned as a phone call to ask her (production, 2026-08-01).

So each capability lives in the domain that lacked it — ``telephony`` for
calls, ``task`` for commitments, ``peer`` for relayed messages — and NOT on
``contact_agent`` with ``serves_domains``. That alternative was measured:
because the planner catalogue is capped, adding three tools reachable from
``contact`` evicted ``reply_email_tool``, ``forward_email_tool`` and
``delete_email_tool`` from the contact+email catalogue, and the three event
mutations from contact+event+email. A read capability must not cost a write one.

Three properties they share, by construction rather than by discipline:

- **one resolution of identity**: all three project the same
  ``RelationsService.build_detail``, so a tool and the relationship card can
  never disagree about who someone is (ADR-185);
- **exact totals**: each block carries the aggregate count next to its page, so
  a cap is stated rather than silently applied (ADR-185 again);
- **the bound is published**: ``limit`` declares its maximum in the manifest,
  so what the validator can clamp is what the planner can read (ADR-184).

They deliberately do NOT apply ``RelationOverviewScope``. That scope answers
"what may a 360° POINT read", written server-side when the user clicks through
from the relationship card. A question typed in the chat carries no such
selection, and refusing to answer it because of a setting made for another
capability would be an invented refusal.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.domains.agents.constants import AGENT_PEER, AGENT_TASK, AGENT_TELEPHONY
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import parse_user_id, validate_runtime_config
from src.domains.relations.schemas import RelationDetail
from src.domains.relations.service import RelationsService

logger = structlog.get_logger(__name__)

#: What one projection produces: the collection name, its page, and the EXACT
#: number of items that exist. Naming the key is what lets the caller build the
#: payload and the log without guessing which dict entry was the page.
type Block = tuple[str, list[dict[str, Any]], int]
type BlockBuilder = Callable[[RelationDetail, int], Block]

#: Person parameter description, shared so the three tools ask for the same thing.
_PERSON_ARG = (
    "Person the question is about, as the user says it (Marie, Marie Dupont, "
    "or a nickname already resolved). Resolved through the SAME name folding "
    "as the relationship card."
)


def _resolved_limit(limit: object) -> int:
    """Clamp ``limit`` into the published bound.

    Out-of-range numeric parameters are REPAIRED, never reported as a defect —
    same doctrine as the planner's parameter clamping (ADR-184).

    The parameter is typed ``int | None``, but a model fills parameters from
    prose: ``"beaucoup"`` and ``""`` both reach here. A page size is
    PRESENTATION, not intent — nothing about the question is lost by falling
    back to the default, whereas raising would deny an answer over a display
    detail.

    Args:
        limit: Requested page size — of any shape, or None for the default.

    Returns:
        A page size within [1, relations_max_items_per_section].
    """
    ceiling: int = settings.relations_max_items_per_section
    if limit is None:
        return ceiling
    try:
        requested = int(limit)  # type: ignore[call-overload]
    except TypeError, ValueError:
        return ceiling
    return max(1, min(requested, ceiling))


async def _relation_detail(user_id: UUID, person_name: str) -> RelationDetail:
    """The CRM's view of one relationship — the single identity resolution."""
    return await RelationsService(user_id).build_detail(person_name)


def _identity(detail: RelationDetail) -> dict[str, Any]:
    """Who the answer is about, so the model never re-guesses the person."""
    return {
        "person": detail.display_name,
        "identity_confidence": detail.identity_confidence.value,
        "is_peer": detail.is_peer,
    }


async def _read_block(
    runtime: ToolRuntime[LiaRuntimeContext, Any],
    person_name: str,
    limit: int | None,
    tool_name: str,
    build_block: BlockBuilder,
) -> UnifiedToolOutput:
    """Shared body of the three tools: resolve, project one block, report.

    Args:
        runtime: LangChain tool runtime (carries the user).
        person_name: Relationship to read.
        limit: Requested page size (clamped).
        tool_name: For the runtime-config validation error and the trace.
        build_block: Projection of the detail into ``(key, page, exact_total)``.

    Returns:
        The block plus the identity it was read for, or a loud failure — never
        an empty page, which would claim there is nothing.
    """
    config = validate_runtime_config(runtime, tool_name)
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)

    try:
        detail = await _relation_detail(user_id, person_name)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        logger.warning(
            f"{tool_name}_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return UnifiedToolOutput.failure(
            message=f"could not read the relationship for '{tool_name}'",
            error_code="relation_read_unavailable",
        )

    # `(key, page, total)` rather than a ready-made dict: reading the page back
    # out of a dict meant trusting insertion order to tell the page from the
    # total, so adding a key would have silently made the log report the wrong
    # number. The builder names what it produced.
    key, page, total = build_block(detail, _resolved_limit(limit))
    payload: dict[str, Any] = {
        **_identity(detail),
        key: page,
        # The EXACT number that exists, next to the page (ADR-185).
        f"{key}_total": total,
    }
    # No PII at INFO: the COUNTS, never the person or the content.
    logger.info(f"{tool_name}_built", user_id=str(user_id), returned=len(page))
    return UnifiedToolOutput.data_success(
        message=f"[{tool_name}] {len(page)} item(s)",
        structured_data=payload,
    )


def _calls_block(detail: RelationDetail, limit: int) -> Block:
    return (
        "calls",
        [
            {
                "objective": call.objective,
                "outcome": call.outcome,
                "summary": call.summary,
                "occurred_at": call.created_at.isoformat() if call.created_at else None,
            }
            for call in (detail.recent_calls or [])[:limit]
        ],
        detail.recent_calls_total,
    )


def _open_loops_block(detail: RelationDetail, limit: int) -> Block:
    return (
        "open_loops",
        [
            {
                "subject": loop.subject,
                "direction": loop.direction,
                "days_open": loop.days_open,
                **({"due_hint": loop.due_hint.isoformat()} if loop.due_hint else {}),
            }
            for loop in (detail.open_loops or [])[:limit]
        ],
        detail.open_loops_total,
    )


def _peer_messages_block(detail: RelationDetail, limit: int) -> Block:
    return (
        "peer_messages",
        [
            {
                "direction": message.direction,
                # Null content is the ledger scrubbing a delivered directive —
                # the exchange happened, its text is simply not the user's to
                # show. Keeping the row without inventing text is the honest form.
                "content": message.content,
                "occurred_at": (message.occurred_at.isoformat() if message.occurred_at else None),
            }
            for message in (detail.peer_messages or [])[:limit]
        ],
        detail.peer_messages_total,
    )


@read_tool(name="get_calls", agent_name=AGENT_TELEPHONY)
async def get_calls_tool(
    person_name: Annotated[str, _PERSON_ARG],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    limit: int | None = None,
) -> UnifiedToolOutput:
    """Past calls with ONE person: objective, outcome, summary, when.

    Args:
        person_name: Person to read the call history of.
        runtime: LangChain tool runtime.
        limit: Page size, clamped to the published maximum.

    Returns:
        The page plus ``calls_total``, the exact number that exist.
    """
    return await _read_block(runtime, person_name, limit, "get_calls_tool", _calls_block)


@read_tool(name="get_open_loops", agent_name=AGENT_TASK)
async def get_open_loops_tool(
    person_name: Annotated[str, _PERSON_ARG],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    limit: int | None = None,
) -> UnifiedToolOutput:
    """Open commitments with ONE person: who owes what, and since when.

    Args:
        person_name: Person to read the open commitments of.
        runtime: LangChain tool runtime.
        limit: Page size, clamped to the published maximum.

    Returns:
        The page plus ``open_loops_total``, the exact number that exist.
    """
    return await _read_block(runtime, person_name, limit, "get_open_loops_tool", _open_loops_block)


@read_tool(name="get_peer_messages", agent_name=AGENT_PEER)
async def get_peer_messages_tool(
    person_name: Annotated[str, _PERSON_ARG],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    limit: int | None = None,
) -> UnifiedToolOutput:
    """Messages relayed through LIA with ONE connected person.

    Args:
        person_name: Connected person to read the relayed messages of.
        runtime: LangChain tool runtime.
        limit: Page size, clamped to the published maximum.

    Returns:
        The page plus ``peer_messages_total`` when both directions were kept.
    """
    return await _read_block(
        runtime, person_name, limit, "get_peer_messages_tool", _peer_messages_block
    )


__all__ = ["get_calls_tool", "get_open_loops_tool", "get_peer_messages_tool"]
