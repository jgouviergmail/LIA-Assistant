"""Vocabulary of the workboard, declared once (ADR-276).

Every string another module compares against lives here: the seven columns in
their display order, the priorities, who a ticket is assigned to, who acts on
it, what an event records, how a run ended, and the stable error codes the API
returns.

Two rules this module exists to enforce:

- **the column order is DERIVED from the enum**, never re-listed. A second list
  is a second authority, and the one that drifts is always the one nobody
  looks at (the ``DOMAIN_REGISTRY`` doctrine applied to a small vocabulary);
- **an error is a CODE, never a sentence.** The frontend maps these to the six
  locales (the peers precedent); a translated string in a payload would be
  right in one language and wrong in five.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class TicketStatus(str, Enum):
    """The columns of the board. Enum order IS column order."""

    IDEA = "idea"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    #: LIA built a draft it may not run unattended; the person confirms it on
    #: the ticket (lot 7). The board draws this column only while it holds one.
    CONFIRMING = "confirming"
    VALIDATING = "validating"
    DONE = "done"


#: Display order of the columns, derived so it cannot diverge from the enum.
STATUS_ORDER: Final[tuple[str, ...]] = tuple(status.value for status in TicketStatus)


def worst_case_run_seconds(timeout_seconds: int, max_attempts: int, retry_delay: int) -> int:
    """The longest a LEGITIMATE run can hold its claim.

    The reaper exists to free the tickets a dead worker still holds, and it
    must never free one a live worker is still working on: two runs on one
    ticket would spend twice and could act twice.

    The trap it closes is arithmetic. The engine bounds ONE ATTEMPT, and a run
    may retry a transient failure — so a run whose attempts each take the full
    timeout holds its claim for ``timeout × attempts`` plus the pauses between
    them, several times longer than the number an operator reads as « the
    timeout ». Deriving it here means the reaper and the settings guard cannot
    disagree about it.

    Args:
        timeout_seconds: Hard bound of ONE attempt.
        max_attempts: Attempts one run may make, the first included.
        retry_delay: Pause between two attempts.

    Returns:
        The age past which a claim is certainly stranded.
    """
    return timeout_seconds * max_attempts + retry_delay * max(0, max_attempts - 1)


#: The word an out-of-turn run stamps its archived rows with
#: (:class:`~src.domains.agents.api.run_origin.RunOrigin.kind`), and therefore
#: the JSON key the retention sweep reads them back by. Declared once: a stamp
#: written under one spelling and purged under another leaves rows nothing ever
#: removes, and nothing would ever say so.
RUN_ORIGIN_KIND: Final[str] = "workboard"

#: The proactive task type every ticket notification carries. It is the key
#: ``ProactiveMessages._TITLES`` is looked up by AND the suffix the frontend
#: prefix-matches (``proactive_workboard``), and TWO surfaces send them — the
#: sweep and the service that hands a ticket over — so it is spelled once.
NOTIFICATION_TASK_TYPE: Final[str] = "workboard"
#: The run a notification names when NO run caused it: the ticket EVENT that
#: did (a handover). A row the registers can join, never a placeholder.
RUN_ID_TICKET_EVENT_PREFIX = "ticket-event:"

#: Statuses that end a ticket's life — ONE, since 2026-09-09. « Annulé » was
#: dropped on the owner's arbitration: a board is read across, and a column
#: that only ever holds abandoned work costs the same width as one that holds
#: live work. What was cancelled is finished — the history says WHY (the
#: ``reason`` on the status event), which is where a motive belongs.
#:
#: Two consequences hang off this set: the board hides such tickets past the
#: reader's « closed older than N days » filter, and the retention sweep (lot 2)
#: removes the hidden run transcripts of a ticket closed for longer than the
#: retention window.
CLOSED_STATUSES: Final[frozenset[str]] = frozenset({TicketStatus.DONE.value})

#: Statuses a ticket can be in while it still has a future — the complement of
#: :data:`CLOSED_STATUSES`, derived rather than re-listed.
OPEN_STATUSES: Final[frozenset[str]] = frozenset(STATUS_ORDER) - CLOSED_STATUSES


class TicketPriority(str, Enum):
    """Four levels, matching the frontend's ``priorityTone`` families."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AssigneeKind(str, Enum):
    """Who holds the ticket: a person's own hands, or that person's LIA (D7).

    The pair ``(kind, assignee_user_id)`` covers every case with no branch on
    « whose LIA »: a run always executes on ``assignee_user_id``'s account,
    quota, language and conversation.
    """

    HUMAN = "human"
    LIA = "lia"


class ActorKind(str, Enum):
    """Who did something on a ticket, as the event log and the comments say."""

    USER = "user"
    LIA = "lia"
    PEER = "peer"


class TicketEventKind(str, Enum):
    """What a ticket event records.

    The event log holds what HUMANS did. What LIA did is also in the three
    ADR-263 registers, under the run's own id — the two records never add up
    and are never joined.
    """

    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    PRIORITY_CHANGED = "priority_changed"
    DATES_CHANGED = "dates_changed"
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    FOLLOW_CHANGED = "follow_changed"


class RunOutcome(str, Enum):
    """How the last run of a ticket ended.

    ``skipped_quota`` and ``skipped_busy`` are deliberately NOT failures: a
    quota refusal is not a generation failure, and a run that stood aside for
    a live conversation did nothing wrong (ADR-272's logging rule).
    ``confirming`` is a run that built an action it may not perform alone and
    put it on the ticket for the person to confirm (lot 7).
    """

    SUCCESS = "success"
    WAITING = "waiting"
    CONFIRMING = "confirming"
    FAILED = "failed"
    SKIPPED_QUOTA = "skipped_quota"
    SKIPPED_BUSY = "skipped_busy"


class RunError(str, Enum):
    """Why a run ended without an answer, as a stable code.

    Stored in ``last_run_error`` beside a bounded technical message, and
    resolved to a sentence by the frontend locales — the same doctrine as
    :class:`WorkboardError`, for a different family: these describe a RUN that
    failed, not a request the API refused.
    """

    ASSIGNEE_INACTIVE = "workboard_assignee_inactive"
    EMPTY_ANSWER = "workboard_empty_answer"
    RUN_FAILED = "workboard_run_failed"
    # The reaper released a claim a dead worker held: nobody observed how
    # that run ended, and a card must say THAT rather than repeat the
    # previous run's message under a fresh « failed ».
    RUN_REAPED = "workboard_run_reaped"


class WorkboardError(str, Enum):
    """Stable machine codes of every refusal on the ``/workboard`` surface.

    These are translation keys: renaming one silently breaks six locales at
    once, which is why ``test_error_codes_contract`` pins the whole set.
    """

    PEERS_DISABLED = "workboard_peers_disabled"
    TITLE_REQUIRED = "workboard_title_required"
    TITLE_TOO_LONG = "workboard_title_too_long"
    DESCRIPTION_TOO_LONG = "workboard_description_too_long"
    COMMENT_REQUIRED = "workboard_comment_required"
    COMMENT_TOO_LONG = "workboard_comment_too_long"
    DEPTH_EXCEEDED = "workboard_depth_exceeded"
    PARENT_NOT_OWNED = "workboard_parent_not_owned"
    TOO_MANY_TICKETS = "workboard_too_many_tickets"
    TOO_MANY_CHILDREN = "workboard_too_many_children"
    ASSIGNEE_NOT_CONNECTED = "workboard_assignee_not_connected"
    CROSS_ACCOUNT_DELEGATION = "workboard_cross_account_delegation"
    PEER_CANNOT_DELETE = "workboard_peer_cannot_delete"
    PEER_CANNOT_EDIT_FIELD = "workboard_peer_cannot_edit_field"
    PEER_CANNOT_REASSIGN = "workboard_peer_cannot_reassign"
    RUN_NOW_REQUIRES_LIA = "workboard_run_now_requires_lia"
    # Handing a ticket LIA is waiting on back to LIA without a word: the
    # answer IS the comment, and running without one would only ask again.
    ANSWER_REQUIRED = "workboard_answer_required"
    MAX_RUNS_REACHED = "workboard_max_runs_reached"
    STATUS_INVALID = "workboard_status_invalid"
    PRIORITY_INVALID = "workboard_priority_invalid"
    DATES_INVERTED = "workboard_dates_inverted"
    AMBIGUOUS_REFERENCE = "workboard_ambiguous_reference"
