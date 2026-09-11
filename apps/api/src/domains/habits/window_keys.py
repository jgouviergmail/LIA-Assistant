"""Identity of a learned activity window — the ONE producer of a window key.

A claimed window drifting by an hour between two nightly runs must keep its
identity (a block on « weekday mornings » survives 8-10h becoming 7-10h), so
the key is the day class plus the coarse part of day of the window's
ACTIVITY center — never its exact hours, and never its geometric middle: a
21h routine claimed as 21-23h would otherwise be labeled « night » while the
person experiences it as an evening habit.

Two readers share this: the nightly sync that writes the mirror rows
(``service._sync_active_window_habits``) and the consumption predicate that
reads their statuses back (``consumption``). A second wording of the key in
either is how a paused window would keep being served (ADR-255's drift class,
measured 2026-09-11 on the three rhythm consumers).
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domains.habits.rhythm import ClaimedWindow

#: Part-of-day bands, wrap-aware for the night band.
_PARTS_OF_DAY: tuple[tuple[str, int, int], ...] = (
    ("night", 22, 5),
    ("morning", 5, 12),
    ("afternoon", 12, 17),
    ("evening", 17, 22),
)


def part_of_day(hour: float) -> str:
    """Coarse part-of-day label for an hour (wrap-aware for night).

    Args:
        hour: Fractional hour of day (0 ≤ hour < 24).

    Returns:
        ``night`` | ``morning`` | ``afternoon`` | ``evening``.
    """
    for name, start, end in _PARTS_OF_DAY:
        if start < end:
            if start <= hour < end:
                return name
        elif hour >= start or hour < end:
            return name
    return "night"  # unreachable — the parts cover the full circle


def activity_center(window: ClaimedWindow, bin_presence: Sequence[float]) -> float:
    """Presence-weighted center of the ACTIVITY inside a window.

    Args:
        window: The claimed window (≤ 4h — no wrap issue on the offsets).
        bin_presence: 24 per-hour presence values of the window's day class;
            a shorter or empty sequence counts as no presence.

    Returns:
        Fractional hour of the activity center, or the geometric middle when
        the window carries no presence at all.
    """
    length = (window.end_hour - window.start_hour) % 24
    bins = [(window.start_hour + k) % 24 for k in range(length)]
    presence = [bin_presence[b] if b < len(bin_presence) else 0.0 for b in bins]
    total = sum(presence)
    if total <= 0:
        return (window.start_hour + length / 2) % 24
    mean_offset = sum((k + 0.5) * presence[k] for k in range(length)) / total
    return (window.start_hour + mean_offset) % 24


def window_habit_key(class_name: str, window: ClaimedWindow, bin_presence: Sequence[float]) -> str:
    """The mirror-row key of one claimed window, e.g. ``"weekday:morning"``.

    Args:
        class_name: ``weekday`` | ``weekend``.
        window: The claimed window.
        bin_presence: Per-hour presence of that day class.

    Returns:
        Stable identity under hour drift.
    """
    return f"{class_name}:{part_of_day(activity_center(window, bin_presence))}"
