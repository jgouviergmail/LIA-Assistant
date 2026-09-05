"""The live record of a turn, published by its parent (ADR-263, lot 6).

The same shape lot 4 arrived at, for the same measured reason: the collector is
a **live object** the turn's parent publishes, not a value a child sets. A
``ContextVar.set()` inside a child task never reaches its parent — it works in
ReAct, where the loop runs in the parent's context, and silently loses every
pipeline turn, whose nodes run in tasks. Publishing an object and mutating it
is what makes one implementation serve both.

Two honesty rules are built into the defaults rather than left to callers:

- **The outcome starts at ``interrupted``.** A turn that dies without saying
  how it ended must never read as answered. Only an explicit success writes
  ``answered`` — the ADR-263 doctrine ("closed from an explicit result")
  applied to the turn itself.
- **Every note is best-effort and silent when no turn is open.** These helpers
  are called from routing functions and nodes that also run in tests, scripts
  and probes; raising there would turn an observability concern into an outage.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domains.agents.effects.models import DecisionOutcome

#: The turn currently being recorded, or None outside a turn. Holds the OBJECT,
#: never a value: a node mutating it reaches the parent that will write it.
_current_turn: ContextVar[TurnDecision | None] = ContextVar("agent_turn_decision", default=None)


@dataclass
class TurnDecision:
    """What is known about the turn in flight.

    Mutable on purpose — it is the live record nodes enrich as they go, and the
    parent writes exactly once at the end.

    Attributes:
        run_id: The turn. A HITL resumption reuses it, which is what makes the
            write an upsert.
        user_id: Whose turn.
        thread_id: Conversation it belongs to.
        source: Under whose authority it ran.
        execution_mode: pipeline | react | subagent.
        route: What the router decided; None when the turn ended before it.
        plan_step_count: Steps the planner produced; None when no plan was built.
        request_message_id: Pointer to what was asked.
        response_message_id: Pointer to what was answered.
        stop_reason: Why the turn stopped short, when it did.
        outcome: How it ended — ``interrupted`` until something says otherwise.
        started_at: When this segment began.
    """

    run_id: str
    user_id: uuid.UUID | None = None
    thread_id: str = ""
    source: str = "user"
    execution_mode: str = "pipeline"
    route: str | None = None
    plan_step_count: int | None = None
    request_message_id: uuid.UUID | None = None
    response_message_id: uuid.UUID | None = None
    stop_reason: str | None = None
    outcome: DecisionOutcome = DecisionOutcome.INTERRUPTED
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def turn_decision(
    *,
    run_id: str,
    user_id: uuid.UUID,
    thread_id: str,
    execution_mode: str,
    automated: bool,
) -> TurnDecision:
    """Build the record of a turn from what its caller knows.

    A factory rather than a constructor call at the call site: the streaming
    entry point is the codebase's largest function and its worst complexity
    hotspot, and « which authority ran this turn » is a rule about the register,
    not about streaming.

    Args:
        run_id: The turn.
        user_id: Whose turn.
        thread_id: Conversation it belongs to.
        execution_mode: pipeline | react | subagent.
        automated: Whether the turn was started by a scheduled action rather
            than by the person.

    Returns:
        The live record, ready to be published.
    """
    return TurnDecision(
        run_id=run_id,
        user_id=user_id,
        thread_id=thread_id,
        source="scheduled" if automated else "user",
        execution_mode=execution_mode,
    )


def current_turn() -> TurnDecision | None:
    """The turn being recorded, or None outside one.

    Returns:
        The live record.
    """
    return _current_turn.get()


def publish_turn(decision: TurnDecision) -> object:
    """Make a turn the one this context records.

    Args:
        decision: The live record.

    Returns:
        The token to reset with, as ``ContextVar.set`` returns.
    """
    return _current_turn.set(decision)


def reset_turn(token: object) -> None:
    """Stop recording the turn this context published.

    Args:
        token: What :func:`publish_turn` returned.
    """
    _current_turn.reset(token)  # type: ignore[arg-type]


def note_route(route: str) -> None:
    """Record what the router decided.

    Called from the graph's routing function, which also runs in tests and
    probes: silent outside a turn rather than raising.

    Args:
        route: The node the turn was routed to.
    """
    turn = _current_turn.get()
    if turn is not None:
        turn.route = route


def note_plan(step_count: int) -> None:
    """Record how many steps the planner produced.

    Args:
        step_count: Steps in the plan.
    """
    turn = _current_turn.get()
    if turn is not None:
        turn.plan_step_count = step_count


def note_stop_reason(reason: str | None) -> None:
    """Record why the turn stopped short (ADR-263, lot 8).

    Called where the stop condition is ALREADY resolved — ``react_exit_reason``
    is one predicate with two readers (ADR-248 invariant 2), and a register
    computing its own would be a third opinion on the same question.

    ``outcome`` stays what it is: a turn stopped by its budget is
    ``interrupted``, and this says WHY. Two columns, two facts.

    Args:
        reason: The stop condition, or None when the turn ran to its end.
    """
    turn = _current_turn.get()
    if turn is not None and reason:
        turn.stop_reason = reason


def note_request_message(message_id: uuid.UUID | None) -> None:
    """Point at what was asked.

    Args:
        message_id: The archived user message, or None when nothing was archived
            (a resumption, a scheduled turn).
    """
    turn = _current_turn.get()
    if turn is not None and message_id is not None:
        turn.request_message_id = message_id


def note_answered(message_id: uuid.UUID | None = None) -> None:
    """Record that the turn produced an answer.

    The ONLY writer of ``answered``. Everything else leaves the outcome at what
    it was, so a turn that died says so rather than inheriting a success.

    Args:
        message_id: The archived assistant message, when one was archived.
    """
    turn = _current_turn.get()
    if turn is None:
        return
    turn.outcome = DecisionOutcome.ANSWERED
    if message_id is not None:
        turn.response_message_id = message_id


__all__ = [
    "TurnDecision",
    "current_turn",
    "note_answered",
    "note_plan",
    "note_request_message",
    "note_route",
    "note_stop_reason",
    "publish_turn",
    "reset_turn",
    "turn_decision",
]
