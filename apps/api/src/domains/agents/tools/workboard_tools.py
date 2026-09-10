"""Workboard tools — the person's board of tickets, from the chat (ADR-276).

Six capabilities: create a ticket, change one, comment on one, list them, read
one in full, delete one.

**No business rule lives here.** ``WorkboardService`` owns the rights, the
bounds, the transitions and the peer resolution; every tool below turns words
into a call and a refusal into a stable CODE. A tool that decided any of it
again would be a second authority on the same question, and the two would
eventually disagree — the failure the ADR-185 folding rule and the ADR-184
bound rule both describe.

Three consequences of that choice, each visible in the code:

- **a refusal travels as its code**, never as a French sentence. The frontend
  resolves the code from its own locales and the model rephrases it in the
  person's language (ADR-256); composing prose here would be right in one
  language and wrong in five.
- **dates are normalised ONCE**, through ``normalize_user_datetime``: the model
  writes the person's LOCAL intent, sometimes with the wrong offset, and a
  hand-rolled parse here would be a second interpretation of the same instant.
- **a ticket is named by id OR by its exact title**, resolved by
  ``resolve_reference``, which REFUSES an ambiguous title rather than guessing:
  acting on the wrong ticket is worse than asking which one.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.time_utils import normalize_user_datetime
from src.domains.agents.constants import AGENT_TICKET, CONTEXT_DOMAIN_TICKETS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    get_user_preferences,
    validate_runtime_config,
)
from src.domains.agents.workboard.context import ticket_registry_items
from src.domains.users.models import User
from src.domains.workboard.board_queries import AssigneeFilter, BoardFilters
from src.domains.workboard.schemas import CommentCreate, TicketCreate, TicketUpdate
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: What a tool returns when the caller has no account row. Not an expected
#: state — the runtime already validated the session — so it is reported rather
#: than silently treated as « no tickets ».
_NO_ACCOUNT = "The account could not be loaded."


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


def _ticket_summary(ticket: Any) -> dict[str, Any]:
    """The bounded view of a ticket a tool hands back.

    Deliberately narrow: an agent answering « où en est ce ticket » needs the
    column, the priority and the dates — not the whole row, whose description
    can run to thousands of characters the model would pay for twice.

    Args:
        ticket: The row.

    Returns:
        The summary.
    """
    return {
        "id": str(ticket.id),
        "title": ticket.title,
        "status": ticket.status,
        "priority": ticket.priority,
        "assignee_kind": ticket.assignee_kind,
        "start_at": ticket.start_at.isoformat() if ticket.start_at else None,
        "due_at": ticket.due_at.isoformat() if ticket.due_at else None,
    }


async def _actor(db: Any, user_id: UUID) -> User | None:
    """The account row the service acts as.

    Args:
        db: The open session.
        user_id: Who is calling.

    Returns:
        The row, or None when it is gone.
    """
    return await db.get(User, user_id)


async def _assignment(
    service: WorkboardService, owner_id: UUID, assignee: str | None
) -> tuple[str | None, UUID | None]:
    """Read what the model wrote in ``assignee`` into what the service takes.

    Three shapes reach this from the chat and only two are keywords: « me » and
    « lia ». Anything else is a NAME, and resolving it is the service's own
    business — it already owns who may hold a ticket.

    Args:
        service: The bound service.
        owner_id: The board's owner.
        assignee: What the model wrote, or None.

    Returns:
        ``(keyword, user_id)`` — exactly one of the two is set.

    Raises:
        ValidationError: The name matches nobody connected, or several.
    """
    if assignee is None:
        return None, None
    keyword = assignee.strip().lower()
    if keyword in {"me", "lia"}:
        return keyword, None
    return None, await service.resolve_connected_user_id(owner_id, assignee.strip())


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
    title: Annotated[str, "What the ticket is, in the user's own words"],
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
    follow: Annotated[bool | None, "Be told in the chat about this ticket (off by default)"] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Put a ticket on the user's workboard.

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
        runtime: LangChain tool runtime (injected).

    Returns:
        The new ticket, or a typed refusal.
    """
    validated = validate_runtime_config(runtime, "create_ticket_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))
    zone, _language, _locale = await get_user_preferences(runtime)

    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if actor is None:
            return UnifiedToolOutput.failure(message=_NO_ACCOUNT, error_code="NOT_FOUND")
        service = WorkboardService(db)
        try:
            keyword, holder = await _assignment(service, user_id, assignee)
            parent_id = (
                (await service.resolve_reference(user_id, parent_ticket)).id
                if parent_ticket
                else None
            )
            payload = TicketCreate(
                title=title,
                description=description,
                parent_id=parent_id,
                assignee=keyword or "me",
                assignee_user_id=holder,
                **_optional(
                    priority=priority,
                    status=status,
                    follow=follow,
                    start_at=normalize_user_datetime(start_at, zone),
                    due_at=normalize_user_datetime(due_at, zone),
                ),
            )
            ticket = await service.create(actor, payload)
            await db.commit()
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)

    logger.info("workboard_ticket_created_from_chat", user_id=str(user_id))
    return UnifiedToolOutput.action_success(
        message=f"Ticket created: {ticket.title} ({ticket.status}).",
        structured_data={"ticket": _ticket_summary(ticket)},
    )


def _optional(**values: Any) -> dict[str, Any]:
    """Keep only what the model actually said.

    A ``None`` here means « not mentioned », and passing it would overwrite a
    schema default with nothing — the difference between « leave it as it is »
    and « clear it », which the update path spells with its own flags.

    Args:
        **values: Candidate fields.

    Returns:
        The subset that was given.
    """
    return {name: value for name, value in values.items() if value is not None}


@write_tool(name="update_ticket", agent_name=AGENT_TICKET)
async def update_ticket_tool(
    ticket: Annotated[str, "The ticket: its id, or its exact title"],
    status: Annotated[str | None, "Move it to this column"] = None,
    priority: Annotated[str | None, "low | medium | high | urgent"] = None,
    title: Annotated[str | None, "A new title (owner only)"] = None,
    description: Annotated[str | None, "A new description (owner only)"] = None,
    start_at: Annotated[str | None, "A new start date, the user's LOCAL time (ISO 8601)"] = None,
    due_at: Annotated[str | None, "A new due date, the user's LOCAL time (ISO 8601)"] = None,
    assignee: Annotated[str | None, "'me', 'lia', or the exact NAME of a connected user"] = None,
    follow: Annotated[bool | None, "Whether to be told about this ticket in the chat"] = None,
    run_now: Annotated[bool | None, "Ask LIA to run it at the next sweep"] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Change a ticket on the workboard. Only the fields given are touched.

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
        runtime: LangChain tool runtime (injected).

    Returns:
        The ticket as it now stands, or a typed refusal.
    """
    validated = validate_runtime_config(runtime, "update_ticket_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))
    zone, _language, _locale = await get_user_preferences(runtime)

    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if actor is None:
            return UnifiedToolOutput.failure(message=_NO_ACCOUNT, error_code="NOT_FOUND")
        service = WorkboardService(db)
        try:
            row = await service.resolve_reference(user_id, ticket)
            keyword, holder = await _assignment(service, row.owner_user_id, assignee)
            changes = TicketUpdate(
                assignee=keyword,
                assignee_user_id=holder,
                **_optional(
                    status=status,
                    priority=priority,
                    title=title,
                    description=description,
                    follow=follow,
                    start_at=normalize_user_datetime(start_at, zone),
                    due_at=normalize_user_datetime(due_at, zone),
                ),
            )
            row = await service.update(actor, row.id, changes)
            if run_now:
                row = await service.run_now(actor, row.id)
            await db.commit()
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)

    return UnifiedToolOutput.action_success(
        message=f"Ticket updated: {row.title} ({row.status}).",
        structured_data={"ticket": _ticket_summary(row)},
    )


@write_tool(name="comment_ticket", agent_name=AGENT_TICKET)
async def comment_ticket_tool(
    ticket: Annotated[str, "The ticket: its id, or its exact title"],
    body: Annotated[str, "The comment, in the user's own language"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Add a comment to a ticket's thread, where both sides read it.

    Args:
        ticket: Which ticket.
        body: What to write.
        runtime: LangChain tool runtime (injected).

    Returns:
        The comment's id, or a typed refusal.
    """
    validated = validate_runtime_config(runtime, "comment_ticket_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if actor is None:
            return UnifiedToolOutput.failure(message=_NO_ACCOUNT, error_code="NOT_FOUND")
        service = WorkboardService(db)
        try:
            row = await service.resolve_reference(user_id, ticket)
            comment = await service.comment(actor, row.id, CommentCreate(body=body))
            await db.commit()
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)

    return UnifiedToolOutput.action_success(
        message=f"Comment added to {row.title}.",
        structured_data={"comment": {"id": str(comment.id), "ticket_id": str(row.id)}},
    )


@read_tool(name="list_tickets", agent_name=AGENT_TICKET, context_domain=CONTEXT_DOMAIN_TICKETS)
async def list_tickets_tool(
    status: Annotated[str | None, "Only this column"] = None,
    assignee: Annotated[str | None, "'me' | 'lia' | 'peer' | 'all' (default)"] = None,
    priority: Annotated[str | None, "Only this priority"] = None,
    overdue: Annotated[bool | None, "Only tickets past their due date and still open"] = None,
    query: Annotated[str | None, "Only tickets whose title contains this fragment"] = None,
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
        if actor is None:
            return UnifiedToolOutput.failure(message=_NO_ACCOUNT, error_code="NOT_FOUND")
        filters = BoardFilters(
            statuses=(status,) if status else None,
            assignee=_board_side(assignee),
            priorities=(priority,) if priority else None,
            overdue=bool(overdue),
            query=query or None,
        )
        try:
            rows, total, counts = await WorkboardService(db).board(
                actor, filters, limit=page, offset=0
            )
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)
        tickets = [_ticket_summary(row) for row in rows]

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
        if actor is None:
            return UnifiedToolOutput.failure(message=_NO_ACCOUNT, error_code="NOT_FOUND")
        service = WorkboardService(db)
        try:
            row = await service.resolve_reference(user_id, ticket)
            bundle = await service.get(actor, row.id)
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)
        payload = {
            "ticket": {
                **_ticket_summary(bundle.ticket),
                "description": bundle.ticket.description,
            },
            "children": [_ticket_summary(child) for child in bundle.children],
            "comments": [
                {"author": comment.author_kind, "body": comment.body} for comment in bundle.comments
            ],
            "last_run": {
                "outcome": bundle.ticket.last_run_outcome,
                "at": (
                    bundle.ticket.last_run_at.isoformat() if bundle.ticket.last_run_at else None
                ),
                "error": bundle.ticket.last_run_error,
                "cost_eur": (
                    float(bundle.ticket.last_run_cost_eur)
                    if bundle.ticket.last_run_cost_eur is not None
                    else None
                ),
            },
        }

    # The ticket read becomes the CURRENT one (« celui-là ») and the list from
    # the last listing is left alone: a read is not a listing, and « le
    # deuxième » must keep pointing at the board the person was shown.
    output = UnifiedToolOutput.data_success(
        message=f"{payload['ticket']['title']} — {payload['ticket']['status']}.",
        registry_updates=ticket_registry_items(
            [_ticket_summary(bundle.ticket)], tool_name="get_ticket_tool"
        ),
        structured_data=payload,
    )
    output.context_save_mode = ContextSaveMode.CURRENT
    return output


@write_tool(name="delete_ticket", agent_name=AGENT_TICKET)
async def delete_ticket_tool(
    ticket: Annotated[str, "The ticket: its id, or its exact title"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Ask to delete a ticket, with its steps, its comments and its history.

    Nothing is deleted here. This returns a TICKET_DELETE draft the person
    confirms, and :func:`execute_ticket_delete_draft` performs it on the
    confirmed replay — the shape every destructive native tool takes
    (``event_delete``, ``task_delete``, ``reminder_delete``…). ``confirm`` is
    reserved for third-party MCP tools, where the policy is DERIVED from the
    server's own annotations rather than declared, and the generic replay it
    uses carries no runtime a native tool could read its identity from.

    The rights are checked BEFORE asking: a holder who is not the owner may
    not delete, and a card they could only ever have refused would be a
    question with one answer. An unattended run deletes nothing either — the
    gate refuses a ``draft`` policy when nobody is there to answer (ADR-263,
    amended by ADR-276), and the ticket settles « waiting for you ».

    Args:
        ticket: Which ticket.
        runtime: LangChain tool runtime (injected).

    Returns:
        The confirmation draft, or a typed refusal.
    """
    validated = validate_runtime_config(runtime, "delete_ticket_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if actor is None:
            return UnifiedToolOutput.failure(message=_NO_ACCOUNT, error_code="NOT_FOUND")
        service = WorkboardService(db)
        try:
            row = await service.resolve_reference(user_id, ticket)
            row, steps = await service.deletable(actor, row.id)
        except (ValidationError, ResourceNotFoundError) as refused:
            return _refusal(refused)

    return DraftService().create_draft(
        draft_type=DraftType.TICKET_DELETE,
        content={"ticket_id": str(row.id), "title": row.title, "children": steps},
        source_tool="delete_ticket_tool",
    )


async def execute_ticket_delete_draft(
    draft_content: dict[str, Any], user_id: UUID, deps: Any
) -> dict[str, Any]:
    """Delete the ticket the person confirmed.

    Called by ``DraftCritiqueInteraction.process_draft_action`` when the card
    is accepted. The rights are re-checked here rather than trusted from the
    draft: an arbitrary delay separates the question from the answer, and the
    ticket may have changed hands in between.

    Args:
        draft_content: ``{ticket_id, title, children}`` from the draft.
        user_id: The confirming account.
        deps: Tool dependency container (unused: the board is internal).

    Returns:
        ``{success, ticket_id, deleted}``, or a failure naming the code.
    """
    ticket_id = UUID(str(draft_content["ticket_id"]))
    async with get_db_context() as db:
        actor = await _actor(db, user_id)
        if actor is None:
            return {"success": False, "error": _NO_ACCOUNT}
        try:
            removed = await WorkboardService(db).delete(actor, ticket_id)
            await db.commit()
        except (ValidationError, ResourceNotFoundError) as refused:
            return {"success": False, "error": str(getattr(refused, "detail", "") or refused)}

    logger.info(
        "workboard_ticket_delete_draft_executed",
        user_id=str(user_id),
        ticket_id=str(ticket_id),
        removed=removed,
    )
    return {
        "success": True,
        "ticket_id": str(ticket_id),
        # The success sentence quotes it (`DRAFT_SUCCESS_MESSAGES`), and the
        # engine reads it from the RESULT, not from the draft.
        "title": str(draft_content.get("title", "")),
        "deleted": removed,
    }
