"""Who hears about a ticket, and what they are told (ADR-276).

Two decisions live here and NOTHING else: this module opens no connection,
sends nothing and imports no dispatcher. That is not tidiness — ``agents``
imports ``workboard`` from lot 3 on, and the notification dispatcher imports
``agents``, so a domain module that reached for it would close a runtime cycle
(the coupling ratchet counts local imports too, so hiding it in a function
would only hide the edge). The sending goes through
``domains/shared/proactive_sink``; this module says WHAT is sent and to whom.

The rules, and why each one is the way it is:

- **following is per ticket and OFF by default** (D6, the owner's arbitration).
  A board of forty tickets that each announced themselves would train the
  person to ignore the chat, which is the opposite of the feature.
- **« it is waiting for you » answers to the flag too**, and to the HOLDER's
  side of it alone. It did not until 2026-09-09 (D6): a question was held to be
  too important to silence, on the argument that a question nobody hears is a
  ticket that never moves again. Three later lots removed that premise — the
  board draws « À confirmer » as soon as it holds a ticket, the hub badge counts
  what waits on the person, and the heartbeat raises a ticket stopped for longer
  than ``WORKBOARD_NUDGE_WAITING_HOURS`` WITHOUT reading the flag. What was left
  was a chat sentence contradicting the flag's own promise (« LIA travaille en
  silence »), on a flag that is OFF by default. The flag now means what it says,
  and a blocked ticket is still found three other ways (D59).
- **nobody is told what they just did themselves.** The actor is excluded, so
  a peer moving a ticket notifies the owner and not themselves.
- **an assignee is a PERSON, never « LIA »**: a ticket LIA holds has no second
  human side, and the owner is its only reader.
- **« it was handed to you » ignores the flag too**, for the reason the flag
  cannot cover: nobody subscribes to a ticket they do not yet know they hold.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import settings
from src.core.constants import WORKBOARD_NOTIFICATION_EXCERPT_MAX_CHARS
from src.core.i18n_proactive import ProactiveMessages
from src.core.i18n_workboard import WorkboardMessages
from src.domains.workboard.constants import RUN_ID_TICKET_EVENT_PREFIX, AssigneeKind

if TYPE_CHECKING:
    from src.domains.workboard.models import WorkboardTicket


class WorkboardEvent(str, Enum):
    """What a ticket notification is about.

    A bounded vocabulary: the value travels into the notification metadata and
    the frontend switches its action row on it, so a free string here would be
    a rendering nobody wrote.
    """

    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    WAITING = "waiting"
    #: LIA prepared an action it may not perform alone; the person confirms it
    #: on the ticket (lot 7). A question, like ``waiting`` — never progress.
    CONFIRMING = "confirming"
    ASSIGNED = "assigned"


#: Events about LIA's own progress, offered to whichever SIDE subscribed.
FOLLOW_GATED: frozenset[WorkboardEvent] = frozenset(
    {WorkboardEvent.RUN_STARTED, WorkboardEvent.RUN_FINISHED, WorkboardEvent.RUN_FAILED}
)

#: Events that are a QUESTION to the account the run belongs to. Only the
#: holder can answer, so nobody else is offered it — and they are offered it
#: only while they follow the ticket (D59). ``assigned`` is the one event no
#: flag can gate: nobody subscribes to a ticket they do not yet know they hold.
STOPPED_ON_THE_HOLDER: frozenset[WorkboardEvent] = frozenset(
    {WorkboardEvent.WAITING, WorkboardEvent.CONFIRMING}
)


def _human_assignee(ticket: WorkboardTicket) -> UUID | None:
    """The OTHER person holding this ticket, when there is one.

    Returns:
        The assignee's account id, or None when the owner holds it themselves
        or when LIA does.
    """
    if ticket.assignee_kind != AssigneeKind.HUMAN.value:
        return None
    if ticket.assignee_user_id is None or ticket.assignee_user_id == ticket.owner_user_id:
        return None
    return ticket.assignee_user_id


def event_run_id(event_id: UUID) -> str:
    """The run id of a notification no run caused: the ticket event behind it.

    A handover is announced by the service, in the person's own request,
    so there is no sweep to file the register row under. The ASSIGNED event
    is the act itself — a durable row anyone can join — and each handover
    is a new event, so a second one is never a replay of the first.

    Args:
        event_id: The ticket event's id.

    Returns:
        The run id to hand the seam.
    """
    return f"{RUN_ID_TICKET_EVENT_PREFIX}{event_id}"


def recipients_for(
    event: WorkboardEvent, ticket: WorkboardTicket, *, actor_user_id: UUID | None = None
) -> tuple[UUID, ...]:
    """Who is told about this event on this ticket.

    Args:
        event: What happened.
        ticket: The ticket it happened to.
        actor_user_id: The account that caused it, when a person did. Excluded
            from the result: nobody needs to be told what they just did.

    Returns:
        The accounts to notify, owner first, without duplicates.
    """
    if event in STOPPED_ON_THE_HOLDER:
        # The run executes on the holder's account, and the holder is the only
        # one who can answer it — so the OTHER side is never offered it, even
        # subscribed. Their own flag decides whether it reaches the chat at all
        # (D59); the board, the hub badge and the heartbeat carry it either way.
        holder = ticket.effective_assignee_id
        follows = ticket.follow_owner if holder == ticket.owner_user_id else ticket.follow_assignee
        return (holder,) if follows else ()

    if event is WorkboardEvent.ASSIGNED:
        # Nobody can follow a ticket they do not know they hold, so this one
        # ignores the flag too — and it goes to the NEW holder alone: the
        # person who handed it over already knows.
        assignee = _human_assignee(ticket)
        if assignee is None or assignee == actor_user_id:
            return ()
        return (assignee,)

    assignee = _human_assignee(ticket)
    chosen: list[UUID] = []
    if event in FOLLOW_GATED:
        if ticket.follow_owner:
            chosen.append(ticket.owner_user_id)
        if ticket.follow_assignee and assignee is not None:
            chosen.append(assignee)
    return tuple(user_id for user_id in chosen if user_id != actor_user_id)


def board_url() -> str:
    """Where the board lives, on this deployment.

    Here rather than at each caller: the runner and the service both put this
    link in a notification, and two builders would eventually name two
    different boards.
    """
    return f"{settings.frontend_url.rstrip('/')}/dashboard/workboard"


def ticket_url(ticket: WorkboardTicket) -> str:
    """Where one ticket lives, on this deployment.

    Args:
        ticket: The ticket.

    Returns:
        Its absolute URL.
    """
    return f"{board_url()}/{ticket.id}"


def intent_url(ticket: WorkboardTicket, language: str) -> str:
    """The chat link that finishes a run this ticket stopped (ADR-173).

    The sentence is the PERSON's own instruction to their assistant, in an
    ATTENDED turn — so the confirmation the sweep could not obtain is asked for
    properly, as a card. Built per RECIPIENT: two sides of a shared ticket do
    not necessarily read the same language, and an instruction in the wrong one
    is answered in the wrong one.

    Args:
        ticket: The stopped ticket.
        language: The recipient's language.

    Returns:
        The absolute chat URL carrying the instruction.
    """
    from urllib.parse import quote

    sentence = WorkboardMessages.finish_in_chat(ticket.title, str(ticket.id), language)
    return f"{settings.frontend_url.rstrip('/')}/dashboard/chat?intent={quote(sentence)}"


def excerpt_of(comment: str | None) -> str:
    """The beginning of what LIA wrote, short enough for a push notification.

    Args:
        comment: The comment body, or None when the run left none.

    Returns:
        A bounded, single-line excerpt; empty when there is nothing to quote.
    """
    if not comment:
        return ""
    flat = " ".join(comment.split())
    if len(flat) <= WORKBOARD_NOTIFICATION_EXCERPT_MAX_CHARS:
        return flat
    return flat[: WORKBOARD_NOTIFICATION_EXCERPT_MAX_CHARS - 1].rstrip() + "…"


def notification_body(
    event: WorkboardEvent,
    ticket: WorkboardTicket,
    *,
    language: str,
    comment: str | None = None,
    intent_url: str = "",
    ticket_url: str = "",
) -> str:
    """The sentence one recipient reads.

    Args:
        event: What happened.
        ticket: The ticket it happened to.
        language: The recipient's language — two sides of a shared ticket do
            not necessarily read the same one.
        comment: What LIA wrote, when the event carries an answer.
        intent_url: The chat deep link that finishes a stopped run.
        ticket_url: Where the ticket lives — the link a confirmation is
            answered through.

    Returns:
        The localized body.
    """
    return ProactiveMessages.workboard_body(
        event.value,
        ticket.title,
        language,
        excerpt=excerpt_of(comment),
        intent_url=intent_url,
        ticket_url=ticket_url,
    )


def notification_metadata(
    event: WorkboardEvent,
    ticket: WorkboardTicket,
    *,
    board_url: str,
    ticket_url: str,
    intent_url: str = "",
) -> dict[str, str]:
    """What the frontend needs to draw the notification's action row.

    ``type`` is added by the dispatcher (``proactive_workboard``), which is why
    it is absent here: two places writing it is one place too many.

    Args:
        event: What happened — the frontend switches its actions on it.
        ticket: The ticket it happened to.
        board_url: Where the board lives.
        ticket_url: Where this ticket lives.
        intent_url: Present on ``waiting`` only; an empty string elsewhere is
            omitted rather than sent empty.

    Returns:
        The bounded metadata payload.
    """
    payload = {
        "event": event.value,
        "ticket_id": str(ticket.id),
        "ticket_title": ticket.title,
        "board_url": board_url,
        "ticket_url": ticket_url,
    }
    if intent_url:
        payload["intent"] = intent_url
    return payload
