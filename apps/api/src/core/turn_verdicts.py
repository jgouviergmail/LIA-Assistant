"""The silent corrections a turn made to itself (B8).

Six things routinely happen mid-turn that nobody sees, and each of them changes
what comes out:

- a **reasoning level is coerced** because the model refuses the one that was
  configured (ADR-245);
- a **planner parameter is clamped** to a bound the manifest publishes, which
  is a repair and deliberately not an error (ADR-184);
- a **history repair** purges tool calls nobody will ever answer, because the
  provider rejects the whole thread otherwise (ADR-248);
- a **truncated structured output is refused** rather than rescued into a
  shorter document announced as complete (ADR-275);
- a **capability is refused by the gate** because it acts and nobody confirmed
  it (ADR-263);
- a **quota refuses a call**, which is not a generation failure and must never
  read as one (ADR-272).

Every one of them was already counted in Prometheus, where an operator sees a
RATE. A person debugging ONE exchange needs the opposite: which of them
happened in THIS turn. That is what this collector holds — a live list the
turn's parent publishes, drained into the debug panel.

**It lives in `core` on purpose.** The producers are spread across
`infrastructure/llm`, `domains/agents` and `domains/usage_limits`; a sink in
any one of them would invert a layer boundary for the others. Nothing here
imports anything, and `note_verdict` is silent outside a turn, so a probe, a
test or a background task never has to know the collector exists.

The payload is a KIND and a short detail, never a value: a clamped parameter
says which bound moved, not what the person asked for.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

__all__ = [
    "MAX_VERDICTS_PER_TURN",
    "VERDICT_KINDS",
    "TurnVerdict",
    "collected_verdicts",
    "is_collecting_verdicts",
    "note_verdict",
    "verdict_collector",
]

#: What a verdict may be. A CLOSED vocabulary, checked by a test: a kind nobody
#: declared would reach the panel as a word no reader can interpret, and the
#: frontend resolves each of these to a sentence.
VERDICT_KINDS: frozenset[str] = frozenset(
    {
        "reasoning_coerced",
        "parameter_clamped",
        "history_repaired",
        "output_truncated",
        "capability_refused",
        "quota_refused",
    }
)

#: A turn cannot fill the panel with corrections. A loop repairing the same
#: history on every iteration would otherwise grow this without bound; past the
#: cap the count is what matters, not the list.
MAX_VERDICTS_PER_TURN = 50


@dataclass(frozen=True)
class TurnVerdict:
    """One silent correction.

    Attributes:
        kind: One of :data:`VERDICT_KINDS`.
        detail: A short, BOUNDED label — a bound name, a shape, a level. Never
            a value the person supplied, and never free text from a model.
    """

    kind: str
    detail: str | None = None


@dataclass
class _Collector:
    rows: list[TurnVerdict]
    dropped: int = 0


_COLLECTOR: ContextVar[_Collector | None] = ContextVar("turn_verdicts", default=None)


@asynccontextmanager
async def verdict_collector() -> AsyncIterator[list[TurnVerdict]]:
    """Collect the turn's verdicts for the duration of the body.

    Async so it composes with the two register recorders it rides beside — one
    ``async with`` for the turn's whole scope, rather than an extra indentation
    level around the codebase's largest function. It awaits nothing itself.

    Yields:
        The list the producers append to, readable by the caller on exit.
    """
    collector = _Collector(rows=[])
    token = _COLLECTOR.set(collector)
    try:
        yield collector.rows
    finally:
        _COLLECTOR.reset(token)


def note_verdict(kind: str, detail: str | None = None) -> None:
    """Record one silent correction, if a turn is collecting.

    Silent outside a turn rather than raising: these sites run in probes, in
    tests and in background tasks that have no panel to feed, and a correction
    must never be the reason a turn fails.

    Args:
        kind: One of :data:`VERDICT_KINDS`. An undeclared kind is DROPPED, so a
            typo cannot reach the panel as a word nobody can read.
        detail: A short bounded label.
    """
    collector = _COLLECTOR.get()
    if collector is None or kind not in VERDICT_KINDS:
        return
    if len(collector.rows) >= MAX_VERDICTS_PER_TURN:
        collector.dropped += 1
        return
    collector.rows.append(TurnVerdict(kind=kind, detail=detail))


def collected_verdicts() -> Sequence[TurnVerdict]:
    """What has been collected so far, or nothing outside a turn.

    Returns:
        The verdicts, in the order they happened.
    """
    collector = _COLLECTOR.get()
    return () if collector is None else tuple(collector.rows)


def dropped_verdicts() -> int:
    """How many verdicts the cap dropped.

    Returns:
        The count, so a capped list says it is capped rather than implying the
        turn made exactly fifty corrections.
    """
    collector = _COLLECTOR.get()
    return 0 if collector is None else collector.dropped


def is_collecting_verdicts() -> bool:
    """Whether a turn is collecting.

    ``collected_verdicts`` answers ``()`` both inside a turn that corrected
    nothing and outside any turn: « corrected nothing » is a fact about a turn,
    « no turn » is not.

    Returns:
        True while a collector is installed.
    """
    return _COLLECTOR.get() is not None
