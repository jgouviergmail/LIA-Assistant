"""Where each heartbeat source's result lands on the aggregated context.

This was a chain of fourteen ``elif`` branches inside
``ContextAggregator._apply_source_result``: a correspondence table written in
control flow. It cost 35 cyclomatic complexity in a file frozen five logical
lines below its size cap, so adding a source meant either growing a declared
hotspot or redding the size ratchet. Neither is a decision anybody would take
on purpose, which is the sign the shape was wrong rather than the budget.

Three shapes hid in that chain and only one is a plain assignment:

- most sources set ONE field and ANNOUNCE themselves in ``available_sources``,
  which is what the decision prompt reads to know what it may speak about;
- the three anti-redundancy windows set one field and announce NOTHING — they
  carry what LIA has already said, not something new to say;
- ``weather`` and ``activity`` unpack tuples under their own conditions, and
  they stay written out in the aggregator. A table that lied about one entry
  would be worse than the branches it replaced, so they are DECLARED as
  hand-placed rather than quietly absent.

The declarations are checked at import (ADR-085 doctrine — the app refuses to
start on a drift), in three directions: every gateable source must have
somewhere to land, no source may be both table-driven and hand-placed, and
every field named here must actually exist on :class:`HeartbeatContext`. That
last one is what makes ``setattr`` safe: a typo becomes a boot failure instead
of a source that silently lands nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from src.domains.heartbeat.schemas import HeartbeatContext
from src.domains.heartbeat.source_policy import HEARTBEAT_SOURCE_KEYS


@dataclass(frozen=True)
class SourcePlacement:
    """Where one source's result goes, and whether the decision hears about it.

    Attributes:
        field: The :class:`HeartbeatContext` attribute receiving the result.
        announces: Whether the source joins ``available_sources``. False for
            the windows that report what LIA already sent: a past notification
            is context for the decision, never a reason to interrupt again.
    """

    field: str
    announces: bool = True


#: source name -> where its result lands. A falsy result places nothing: an
#: empty list means « the source ran and found nothing », and announcing it
#: would put an empty section in front of the decision.
SOURCE_PLACEMENTS: dict[str, SourcePlacement] = {
    "calendar": SourcePlacement("calendar_events"),
    "tasks": SourcePlacement("pending_tasks"),
    "emails": SourcePlacement("unread_emails"),
    "interests": SourcePlacement("trending_interests"),
    "memories": SourcePlacement("user_memories"),
    "journals": SourcePlacement("journal_entries"),
    "health_signals": SourcePlacement("health_signals"),
    "birthdays": SourcePlacement("upcoming_birthdays"),
    "open_loops": SourcePlacement("open_loops"),
    "habits": SourcePlacement("habits"),
    "departure": SourcePlacement("departure_advice"),
    "workboard": SourcePlacement("workboard"),
    "recent_heartbeats": SourcePlacement("recent_heartbeats", announces=False),
    "recent_interests": SourcePlacement("recent_interest_notifications", announces=False),
    "recent_other": SourcePlacement("recent_other_notifications", announces=False),
}

#: Sources the aggregator places itself, each because one result carries
#: several values under their own conditions:
#:
#: - ``weather`` unpacks four (a current reading, forecast changes, and the
#:   provenance of the location) and announces itself only on the CURRENT
#:   reading — a forecast change with nothing to report now is not a source;
#: - ``activity`` unpacks a pair (when somebody last spoke, and how long ago)
#:   and never announces: how long ago somebody spoke is not news.
HAND_PLACED_SOURCES: frozenset[str] = frozenset({"weather", "activity"})

#: Every name the aggregator may hand to the dispatcher.
DISPATCHED_SOURCES: frozenset[str] = frozenset(SOURCE_PLACEMENTS) | HAND_PLACED_SOURCES


def assert_placements_complete() -> None:
    """Fail loudly when a source has nowhere to land, or lands nowhere real.

    Called at import (so the boot carries it) and from a unit test.

    Raises:
        RuntimeError: A gateable source with no placement, a source declared
            twice, or a placement naming a field the context does not have.
    """
    both = sorted(set(SOURCE_PLACEMENTS) & HAND_PLACED_SOURCES)
    if both:
        raise RuntimeError(f"Heartbeat sources declared both table-driven and hand-placed: {both}.")

    orphans = sorted(HEARTBEAT_SOURCE_KEYS - DISPATCHED_SOURCES)
    if orphans:
        raise RuntimeError(
            "Heartbeat sources a user can switch off but whose result lands " f"nowhere: {orphans}."
        )

    known = {field.name for field in fields(HeartbeatContext)}
    unknown = sorted(
        f"{name} -> {placement.field}"
        for name, placement in SOURCE_PLACEMENTS.items()
        if placement.field not in known
    )
    if unknown:
        raise RuntimeError(f"Heartbeat placements naming no context field: {unknown}.")


assert_placements_complete()


__all__ = [
    "DISPATCHED_SOURCES",
    "HAND_PLACED_SOURCES",
    "SOURCE_PLACEMENTS",
    "SourcePlacement",
    "assert_placements_complete",
]
