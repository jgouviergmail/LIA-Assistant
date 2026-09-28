"""The session's running order: every slot decided, when it airs, and what follows it.

The grid decides ONE next segment from what has aired and when the next one will
start; a session needs that answer before the segment exists, because the
segment is produced ahead of the listener. The running order keeps, per slot,
its format and its air time — PROJECTED while it waits (the previous slot's end,
plus the station's music between two programmes, ADR-324 decision 36), REPORTED
once the player says it started — and re-anchors every later projection on each
report, so a clock mark (« the nine o'clock bulletin ») is decided on the best
estimate of when it will really be heard.

The order is planned ONE SLOT beyond the segment in production for scheduling.
A writer names that successor only if its audio is already ready: a merely
planned programme may fail and disappear before the listener hears it.
Planning costs nothing (the grid is pure); producing does.

Pure: the orchestrator keeps the slots (a small list) and replaces them with
what these functions return.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.grid import AiredSegment, GridDecision


@dataclass(frozen=True, slots=True)
class Slot:
    """One programme of the session.

    Attributes:
        seq: Its place in the session, from 1.
        format: What it is.
        station_id: Whether it names the station.
        air_at: When it airs — reported once it did, projected before (UTC).
        duration_s: Its real duration once produced, its format's target before.
        reported: Whether ``air_at`` is the player's report.
        clock_mark: The mark it was scheduled for, if any.
    """

    seq: int
    format: RadioFormat
    station_id: bool
    air_at: datetime
    duration_s: float
    reported: bool = False
    clock_mark: datetime | None = None

    def __post_init__(self) -> None:
        if self.air_at.tzinfo is None:
            raise ValueError("air_at must be timezone-aware")
        object.__setattr__(self, "air_at", self.air_at.astimezone(UTC))

    @property
    def ends_at(self) -> datetime:
        """When it stops airing."""
        return self.air_at + timedelta(seconds=self.duration_s)


def next_air_at(
    slots: Sequence[Slot], *, now: datetime, first_delay_s: float, gap_s: float = 0.0
) -> datetime:
    """When the next slot will start airing.

    Args:
        slots: The running order.
        now: The current instant (timezone-aware).
        first_delay_s: How long the first segment takes to be ready.
        gap_s: The station's music between two programmes (none before the first).

    Returns:
        The end of the last slot and the music after it, never earlier than now
        (a late segment is dead air, filled by the music too, and airs after it).
    """
    now_utc = now.astimezone(UTC)
    if not slots:
        return now_utc + timedelta(seconds=first_delay_s)
    return max(slots[-1].ends_at + timedelta(seconds=gap_s), now_utc)


def append(slots: Sequence[Slot], decision: GridDecision, air_at: datetime) -> tuple[Slot, ...]:
    """The running order with the grid's next decision at its end.

    Args:
        slots: The running order.
        decision: What the grid chose.
        air_at: When it airs (from :func:`next_air_at`).

    Returns:
        The new running order.
    """
    slot = Slot(
        seq=(slots[-1].seq + 1) if slots else 1,
        format=decision.format,
        station_id=decision.station_id_due,
        air_at=air_at,
        duration_s=float(FORMAT_SPECS[decision.format].target_seconds),
        clock_mark=decision.clock_mark,
    )
    return (*slots, slot)


def _reproject(slots: Sequence[Slot], start: int, gap_s: float) -> tuple[Slot, ...]:
    """Shift every unreported slot after ``start`` to follow its predecessor and the music."""
    result = list(slots)
    gap = timedelta(seconds=gap_s)
    for index in range(start + 1, len(result)):
        if result[index].reported:
            continue
        result[index] = replace(result[index], air_at=result[index - 1].ends_at + gap)
    return tuple(result)


def _index(slots: Sequence[Slot], seq: int) -> int | None:
    return next((i for i, slot in enumerate(slots) if slot.seq == seq), None)


def mark_produced(
    slots: Sequence[Slot], seq: int, duration_s: float, *, gap_s: float = 0.0
) -> tuple[Slot, ...]:
    """Record a slot's real duration and move what follows it.

    Args:
        slots: The running order.
        seq: The produced slot.
        duration_s: Its measured duration.
        gap_s: The station's music between two programmes.

    Returns:
        The new running order (unchanged when ``seq`` is unknown).
    """
    index = _index(slots, seq)
    if index is None:
        return tuple(slots)
    updated = [*slots]
    updated[index] = replace(slots[index], duration_s=duration_s)
    return _reproject(updated, index, gap_s)


def mark_aired(
    slots: Sequence[Slot], seq: int, started_at: datetime, *, gap_s: float = 0.0
) -> tuple[Slot, ...]:
    """Record when the player started a slot and re-anchor what follows.

    Args:
        slots: The running order.
        seq: The slot the player started.
        started_at: When it started (timezone-aware).
        gap_s: The station's music between two programmes.

    Returns:
        The new running order (unchanged when ``seq`` is unknown).
    """
    index = _index(slots, seq)
    if index is None:
        return tuple(slots)
    updated = [*slots]
    updated[index] = replace(slots[index], air_at=started_at, reported=True)
    return _reproject(updated, index, gap_s)


def remove(slots: Sequence[Slot], seq: int, *, gap_s: float = 0.0) -> tuple[Slot, ...]:
    """The running order without a slot that will never air; what follows moves up.

    Args:
        slots: The running order.
        seq: The slot to drop (a production that failed).
        gap_s: The station's music between two programmes.

    Returns:
        The new running order (unchanged when ``seq`` is unknown).
    """
    index = _index(slots, seq)
    if index is None:
        return tuple(slots)
    kept = [*slots[:index], *slots[index + 1 :]]
    if index < len(kept) and not kept[index].reported:
        kept[index] = replace(kept[index], air_at=slots[index].air_at)
    return _reproject(kept, index, gap_s)


def following(slots: Sequence[Slot], seq: int) -> RadioFormat | None:
    """The format planned right after ``seq``, if already decided."""
    index = _index(slots, seq)
    if index is None or index + 1 >= len(slots):
        return None
    return slots[index + 1].format


def hand_over_to(slots: Sequence[Slot], seq: int, *, ready: Collection[int]) -> RadioFormat | None:
    """The programme the writer of ``seq`` may announce, if any.

    A planned successor can fail production and disappear from the running
    order. Announce it only once its audio is ready. Never announce the
    farewell: a projected one can still be withdrawn before it airs.
    """
    index = _index(slots, seq)
    if index is None or index + 1 >= len(slots):
        return None
    successor = slots[index + 1]
    if successor.seq not in ready or successor.format is RadioFormat.SIGN_OFF:
        return None
    return successor.format


def preceding(slots: Sequence[Slot], seq: int) -> RadioFormat | None:
    """The format right before ``seq``, if any."""
    index = _index(slots, seq)
    if index is None or index == 0:
        return None
    return slots[index - 1].format


def aired_segments(slots: Sequence[Slot]) -> tuple[AiredSegment, ...]:
    """The running order as the grid reads it (planned slots count as aired)."""
    return tuple(AiredSegment(slot.format, slot.air_at, slot.station_id) for slot in slots)


__all__ = [
    "Slot",
    "aired_segments",
    "append",
    "following",
    "hand_over_to",
    "mark_aired",
    "mark_produced",
    "next_air_at",
    "preceding",
    "remove",
]
