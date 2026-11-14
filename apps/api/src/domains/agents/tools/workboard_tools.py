"""Workboard tools — the person's board of tickets, from the chat (ADR-276).

Seven capabilities: create a ticket, change one, comment on one, list them,
read one in full, delete one — and list the CATEGORIES the board is split into.

**No business rule lives here.** ``WorkboardService`` owns the rights, the
bounds, the transitions and the peer resolution; every tool below turns words
into a call and a refusal into a stable CODE. A tool that decided any of it
again would be a second authority on the same question, and the two would
eventually disagree — the failure the ADR-185 folding rule and the ADR-184
bound rule both describe.

Four consequences of that choice, each visible in the code:

- **a refusal travels as its code**, never as a French sentence. The frontend
  resolves the code from its own locales and the model rephrases it in the
  person's language (ADR-256); composing prose here would be right in one
  language and wrong in five. True of every tool here: the creation and the
  readers answer it themselves, and the update, the comment and the deletion
  — which ask through the native tools' shared preparation, whose own answer
  names no cause — let it out through ``workboard_refusal``.
- **dates are normalised ONCE**, through ``normalize_user_datetime``: the model
  writes the person's LOCAL intent, sometimes with the wrong offset, and a
  hand-rolled parse here would be a second interpretation of the same instant.
- **a ticket is named by id OR by its exact title**, resolved by
  ``resolve_reference``, which REFUSES an ambiguous title rather than guessing:
  acting on the wrong ticket is worse than asking which one.
- **a category is read, filtered on and filed under — never administered.** A
  tool names a ticket's category, narrows the board to one and files a ticket
  under one, always by the NAME the person uses. Creating, renaming, reordering
  and deleting a category happen on the board (owner arbitration, 2026-11-11):
  no tool here does it, and the manifests say so.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import Field, StrictBool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
    raise_not_found_or_unauthorized,
)
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.workboard_create import creation_access
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateInput
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdateInput
from src.domains.agents.constants import AGENT_TICKET, CONTEXT_DOMAIN_TICKETS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    validate_runtime_config,
)
from src.domains.agents.tools.workboard_comment_tool import propose_workboard_comment
from src.domains.agents.tools.workboard_creation_tool import propose_workboard_creation
from src.domains.agents.tools.workboard_delete_tool import propose_workboard_delete
from src.domains.agents.tools.workboard_update_tool import propose_workboard_update
from src.domains.agents.workboard.category_manifest import categories_managed_from
from src.domains.agents.workboard.context import ticket_registry_items
from src.domains.users.models import User
from src.domains.workboard.board_queries import AssigneeFilter, BoardFilters
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


def _refusal(error: Exception) -> UnifiedToolOutput:
    """Turn a service refusal into a typed tool failure.

    The service raises with a STABLE code (``workboard_*``); it travels
    untouched so the frontend can translate it and the model can rephrase it.
    Composing a sentence here would freeze one language into a payload.

    Args:
        error: What the service raised.

    Returns:
        The typed failure.
    """
    code = str(getattr(error, "detail", "") or error) or "WORKBOARD_ERROR"
    return UnifiedToolOutput.failure(
        message=code,
        error_code="INVALID_INPUT" if isinstance(error, ValidationError) else "NOT_FOUND",
        metadata={"workboard_error": code},
    )


def _ticket_summary(ticket: Any, names: dict[UUID, str]) -> dict[str, Any]:
    """The bounded view of a ticket a tool hands back.

    Deliberately narrow: an agent answering « where is this ticket at » needs the
    column, the priority, the category and the dates — not the whole row, whose
    description can run to thousands of characters the model would pay for twice.

    Args:
        ticket: The row.
        names: Name of each category the page's tickets are filed under.

    Returns:
        The summary. ``category`` is the NAME — never an id, which says nothing
        to a model or a person — or None for a ticket filed under no category
        of the reader's board: nothing at all, or, for the step of a ticket
        held for somebody else, a lane of its owner's the reader does not see.
    """
    return {
        "id": str(ticket.id),
        "title": ticket.title,
        "status": ticket.status,
        "priority": ticket.priority,
        "assignee_kind": ticket.assignee_kind,
        "category": names.get(ticket.category_id) if ticket.category_id else None,
        "start_at": ticket.start_at.isoformat() if ticket.start_at else None,
        "due_at": ticket.due_at.isoformat() if ticket.due_at else None,
    }


async def _actor(db: AsyncSession, user_id: UUID) -> User | UnifiedToolOutput:
    """Historical readers use the same fresh application/Workboard/account authority."""
    try:
        return await creation_access(db, user_id)
    except AuthorizationError as refused:
        return UnifiedToolOutput.failure(
            message="Workboard reading refused.", error_code=application_access_error_code(refused)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Workboard reading unavailable.", error_code="DEPENDENCY_ERROR"
        )


def _board_side(assignee: str | None) -> AssigneeFilter:
    """Which side of the board the reader asked for.

    An unknown word reads as « all » rather than refusing: a filter the model
    mis-spelled must not turn « what is on my board » into an error message.

    Args:
        assignee: What the model wrote, or None.

    Returns:
        A declared filter value.
    """
    if assignee in ("me", "lia", "peer", "all"):
        return assignee
    return "all"


@write_tool(name="create_ticket", agent_name=AGENT_TICKET)
async def create_ticket_tool(
    title: Annotated[str | None, "Legacy title; use request for the full current UI schema"] = None,
    description: Annotated[
        str | None,
        "What it is about. When assignee='lia' this IS the brief LIA will run.",
    ] = None,
    priority: Annotated[str | None, "low | medium | high | urgent"] = None,
    status: Annotated[
        str | None,
        "The column: idea, todo, in_progress, waiting, confirming, validating, done",
    ] = None,
    start_at: Annotated[str | None, "When work may start, the user's LOCAL time (ISO 8601)"] = None,
    due_at: Annotated[str | None, "When it is due, the user's LOCAL time (ISO 8601)"] = None,
    assignee: Annotated[
        str | None, "'me' (default), 'lia', or the exact NAME of a connected user"
    ] = None,
    parent_ticket: Annotated[
        str | None, "The ticket this is a step of, by id or exact title (ONE level)"
    ] = None,
    follow: Annotated[
        StrictBool | None, "Be told in the chat about this ticket (off by default)"
    ] = None,
    category: Annotated[
        str | None, "File it under this category: the exact NAME of one of the user's own"
    ] = None,
    request: WorkboardCreateInput | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare mandatory confirmation for an exact ticket creation.

    Args:
        title: What the ticket is.
        description: What it is about; the brief when LIA holds it.
        priority: How urgent it is.
        status: Which column to create it in.
        start_at: When work may start, in the user's local time.
        due_at: When it is due, in the user's local time.
        assignee: Who holds it.
        parent_ticket: The ticket this one is a step of.
        follow: Whether to be told about it in the chat.
        category: The name of the user's own category to file it under.
        request: Full current source UI configuration; exclusive with legacy fields.
        runtime: LangChain tool runtime (injected).

    Returns:
        A pending native confirmation, with no ticket creation.
    """
    return await propose_workboard_creation(
        runtime,
        request,
        {
            "title": title,
            "description": description,
            "priority": priority,
            "status": status,
            "start_at": start_at,
            "due_at": due_at,
            "assignee": assignee,
            "parent_ticket": parent_ticket,
            "follow": follow,
            "category": category,
        },
    )


@write_tool(name="update_ticket", agent_name=AGENT_TICKET)
async def update_ticket_tool(
    ticket: Annotated[
        str | None, "Legacy ticket id or exact title; use request for the full UI schema"
    ] = None,
    status: Annotated[str | None, "Move it to this column"] = None,
    priority: Annotated[str | None, "low | medium | high | urgent"] = None,
    title: Annotated[str | None, "A new title (owner only)"] = None,
    description: Annotated[str | None, "A new description (owner only)"] = None,
    start_at: Annotated[str | None, "A new start date, the user's LOCAL time (ISO 8601)"] = None,
    due_at: Annotated[str | None, "A new due date, the user's LOCAL time (ISO 8601)"] = None,
    assignee: Annotated[str | None, "'me', 'lia', or the exact NAME of a connected user"] = None,
    follow: Annotated[StrictBool | None, "Whether to be told about this ticket in the chat"] = None,
    run_now: Annotated[StrictBool | None, "Ask LIA to run it at the next sweep"] = None,
    category: Annotated[
        str | None, "File it under this category: the exact NAME of one of the user's own"
    ] = None,
    clear_category: Annotated[
        StrictBool | None, "Take it out of its category (owner only); never with category"
    ] = None,
    request: WorkboardUpdateInput | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare mandatory confirmation for a source ticket update, move or run request.

    Args:
        ticket: Which ticket.
        status: A new column.
        priority: A new priority.
        title: A new title.
        description: A new description.
        start_at: A new start date, in the user's local time.
        due_at: A new due date, in the user's local time.
        assignee: Who holds it now.
        follow: Whether to be told about it.
        run_now: Ask LIA to run it at the next sweep.
        category: The name of the user's own category to file it under.
        clear_category: Take it out of its category.
        request: Full current UI schema; exclusive with legacy fields.
        runtime: LangChain tool runtime (injected).

    Returns:
        A native confirmation; no changes or notifications before approval.
    """
    return await propose_workboard_update(
        ticket,
        runtime,
        request,
        {
            "status": status,
            "priority": priority,
            "title": title,
            "description": description,
            "start_at": start_at,
            "due_at": due_at,
            "assignee": assignee,
            "follow": follow,
            "run_now": run_now,
            "category": category,
            "clear_category": clear_category,
        },
    )


@write_tool(name="comment_ticket", agent_name=AGENT_TICKET)
async def comment_ticket_tool(
    ticket: Annotated[str, "The ticket: its id, or its exact title"],
    body: Annotated[
        str,
        Field(
            description="The literal comment, in the user's own language",
            min_length=1,
            max_length=settings.workboard_comment_max_chars,
        ),
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare mandatory confirmation for a literal comment and any pending-answer consequence.

    Args:
        ticket: Which ticket.
        body: What to write.
        runtime: LangChain tool runtime (injected).

    Returns:
        A native confirmation; nothing is posted or approved here.
    """
    return await propose_workboard_comment(ticket, body, runtime)


@read_tool(name="list_tickets", agent_name=AGENT_TICKET, context_domain=CONTEXT_DOMAIN_TICKETS)
async def list_tickets_tool(
    status: Annotated[str | None, "Only this column"] = None,
    assignee: Annotated[str | None, "'me' | 'lia' | 'peer' | 'all' (default)"] = None,
    priority: Annotated[str | None, "Only this priority"] = None,
    overdue: Annotated[bool | None, "Only tickets past their due date and still open"] = None,
    query: Annotated[str | None, "Only tickets whose title contains this fragment"] = None,
    category: Annotated[str | None, "Only tickets filed under the category of this NAME"] = None,
    uncategorized: Annotated[bool | None, "Only tickets filed under no category"] = None,
    limit: Annotated[int | None, "How many to return (the EXACT total comes too)"] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """List what is on the board, with the EXACT total beside the page.

    The total is an aggregate over the same filter, never the length of the
    page (ADR-185): a count shown to somebody is exact or it does not exist.

    Args:
        status: Narrow to one column.
        assignee: Narrow to one side.
        priority: Narrow to one priority.
        overdue: Only what is late.
        query: A fragment of the title.
        category: Narrow to the lanes of this name on the user's board.
        uncategorized: Narrow to what is filed under nothing; with ``category``
            the two widen each other, as on the board.
        limit: Page size.
        runtime: LangChain tool runtime (injected).

    Returns:
        The page, the exact total and the per-column counts.
    """
    validated = validate_runtime_config(runtime, "list_tickets_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))
    page = max(1, min(int(limit or 20), 100))

    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if isinstance(actor, UnifiedToolOutput):
            return actor
        try:
            service = WorkboardService(db)
            # A name not on the board is REFUSED, before anything is read: an
            # empty page would say « no ticket in it », which is another fact.
            lanes = await service.categories.visible_named(user_id, category) if category else None
            filters = BoardFilters(
                statuses=(status,) if status else None,
                assignee=_board_side(assignee),
                priorities=(priority,) if priority else None,
                overdue=bool(overdue),
                query=query or None,
                categories=lanes,
                uncategorized=bool(uncategorized),
            )
            rows, total, counts = await service.board(actor, filters, limit=page, offset=0)
            if await service.repo.count_visible([row.id for row in rows], user_id) != len(rows):
                raise_not_found_or_unauthorized("workboard", user_id)
            names = await service.categories.names_for(user_id, rows)
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)
        tickets = [_ticket_summary(row, names) for row in rows]
        checked = await _actor(db, user_id)
        if isinstance(checked, UnifiedToolOutput):
            return checked

    return UnifiedToolOutput.data_success(
        message=f"{total} ticket(s) match; showing {len(tickets)}.",
        registry_updates=ticket_registry_items(tickets, tool_name="list_tickets_tool"),
        structured_data={"tickets": tickets, "total": total, "counts": counts},
    )


@read_tool(name="get_ticket", agent_name=AGENT_TICKET, context_domain=CONTEXT_DOMAIN_TICKETS)
async def get_ticket_tool(
    ticket: Annotated[str, "The ticket: its id, or its exact title"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read one ticket in full: its steps, its thread and its last run.

    Args:
        ticket: Which ticket.
        runtime: LangChain tool runtime (injected).

    Returns:
        The ticket, its children, its comments and what the last run produced.
    """
    validated = validate_runtime_config(runtime, "get_ticket_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if isinstance(actor, UnifiedToolOutput):
            return actor
        service = WorkboardService(db)
        try:
            row = await service.resolve_reference(user_id, ticket)
            bundle = await service.get(actor, row.id)
            if await service.repo.get_visible(bundle.ticket.id, user_id) is None:
                raise_not_found_or_unauthorized("ticket", bundle.ticket.id)
            names = await service.categories.names_for(user_id, [bundle.ticket, *bundle.children])
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)
        summary = _ticket_summary(bundle.ticket, names)
        last_run: dict[str, str | float | None] = {
            "outcome": bundle.ticket.last_run_outcome,
            "at": (bundle.ticket.last_run_at.isoformat() if bundle.ticket.last_run_at else None),
            "error": bundle.ticket.last_run_error,
            "cost_eur": (
                float(bundle.ticket.last_run_cost_eur)
                if bundle.ticket.last_run_cost_eur is not None
                else None
            ),
        }
        payload = {
            "ticket": {**summary, "description": bundle.ticket.description},
            "children": [_ticket_summary(child, names) for child in bundle.children],
            "comments": [
                {"author": comment.author_kind, "body": comment.body} for comment in bundle.comments
            ],
            "last_run": last_run,
        }
        checked = await _actor(db, user_id)
        if isinstance(checked, UnifiedToolOutput):
            return checked

    # The ticket read becomes the CURRENT one (« that one ») and the list from
    # the last listing is left alone: a read is not a listing, and « the second
    # one » must keep pointing at the board the person was shown.
    output = UnifiedToolOutput.data_success(
        message=f"{payload['ticket']['title']} — {payload['ticket']['status']}.",
        registry_updates=ticket_registry_items(
            [summary],
            tool_name="get_ticket_tool",
            display_by_id={
                str(bundle.ticket.id): {
                    "description": payload["ticket"]["description"],
                    "children": payload["children"],
                    "comments": payload["comments"],
                    "last_run": {
                        **last_run,
                        "tokens_in": getattr(bundle.ticket, "last_run_tokens_in", None),
                        "tokens_out": getattr(bundle.ticket, "last_run_tokens_out", None),
                    },
                }
            },
        ),
        structured_data=payload,
    )
    output.context_save_mode = ContextSaveMode.CURRENT
    return output


@read_tool(name="list_ticket_categories", agent_name=AGENT_TICKET)
async def list_ticket_categories_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """List the categories the board is split into, with the EXACT count of each.

    Read-only, and the only thing a tool does with the categories themselves:
    the user creates, renames, reorders and deletes them on the board.

    Every count is an aggregate over the WHOLE visible board (ADR-185), the
    one the board's own lanes show. A board with no category answers an empty
    list and NO count of unfiled tickets: with no lane there is no aggregate,
    and « 0 » would be a figure nobody counted.

    The result also says WHERE the user administers categories, the page and
    the button named in the turn's language as the person's screen shows them.
    A request to create or rename one lands here, and the model that writes
    the pipeline's answer reads this data, never a tool's description.

    Args:
        runtime: LangChain tool runtime (injected).

    Returns:
        Each category with whether it is the user's own and how many tickets
        it holds, how many tickets are filed under none, and where the user
        administers categories.
    """
    validated = validate_runtime_config(runtime, "list_ticket_categories_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if isinstance(actor, UnifiedToolOutput):
            return actor
        lanes = await WorkboardService(db).categories.lanes(actor, BoardFilters())
        checked = await _actor(db, user_id)
        if isinstance(checked, UnifiedToolOutput):
            return checked

    categories = [
        {
            "name": lane.name,
            # Only the user's OWN categories can take one of their tickets;
            # another person's is the lane of a ticket the user holds for them.
            "mine": lane.owner_user_id == user_id,
            "tickets": sum(lane.counts_by_status.values()),
        }
        for lane in lanes
        if lane.category_id is not None
    ]
    data: dict[str, Any] = {
        "categories": categories,
        # The turn's own language: the one the answer is written in, so the two
        # labels it quotes are the ones the person's screen shows.
        "managed_from": categories_managed_from(runtime.context.language),
    }
    if lanes:
        data["unfiled_tickets"] = sum(
            sum(lane.counts_by_status.values()) for lane in lanes if lane.category_id is None
        )
    return UnifiedToolOutput.data_success(
        message=f"{len(categories)} categor{'y' if len(categories) == 1 else 'ies'} on the board.",
        structured_data=data,
    )


@write_tool(name="delete_ticket", agent_name=AGENT_TICKET)
async def delete_ticket_tool(
    ticket: Annotated[str, "The ticket: its id, or its exact title"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Ask to delete a ticket, with its steps, its comments and its history.

    Nothing is deleted here. The native application draft names the exact
    owned subtree and its counts. Confirmation rechecks that scope, current
    capability and actual persisted removal. Legacy TICKET_DELETE cards are
    refused as stale: their stored content cannot prove this exact scope.

    The rights are checked BEFORE asking: a holder who is not the owner may
    not delete, and a card they could only ever have refused would be a
    question with one answer. An unattended run deletes nothing either — the
    gate refuses a ``draft`` policy when nobody is there to answer (ADR-263,
    amended by ADR-276), and the ticket settles "waiting for you".

    Args:
        ticket: Which ticket.
        runtime: LangChain tool runtime (injected).

    Returns:
        The confirmation draft, or a typed refusal.
    """
    return await propose_workboard_delete(ticket, runtime)


async def execute_ticket_delete_draft(
    draft_content: dict[str, object], user_id: UUID, deps: object
) -> dict[str, object]:
    """Refuse persisted legacy cards; a new native proposal supplies exact consent.

    Legacy content carries only a title and child count, without a frozen
    subtree or command identity. It cannot be upgraded after confirmation
    without asking the person to approve the newly observed scope. Retain the
    registered reader so checkpoint resumes receive a finite refusal rather
    than resolving to a missing executor.
    """
    return {"success": False, "error": "STALE_STATE"}
