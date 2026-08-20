"""Pure streak computation over activity days (Lot 1-A4, ADR-234 program).

I/O-free (same doctrine as ``rhythm.py``/``verdicts.py``: importable
without an environment). The streak is a DISPLAY fact derived from the
ledger's local dates — it never feeds the detection thresholds, whose
calibration stays authoritative (ADR-214).

Grace rule: today's absence does not break a streak (the day is not over);
a streak is *current* when it ends today or yesterday.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class StreakSummary:
    """Streak facts derived from the activity ledger."""

    current: int
    longest: int
    milestone_reached: int | None
    next_milestone: int | None


def compute_streaks(
    active_days: Iterable[date],
    *,
    today: date,
    milestones: Sequence[int],
) -> StreakSummary:
    """Compute current/longest streaks and milestone positions.

    Args:
        active_days: Local dates with recorded activity (any order,
            duplicates tolerated). Future dates are ignored — a corrupted
            or timezone-shifted row must not fabricate a streak.
        today: The user's LOCAL today (timezone resolved by the caller).
        milestones: Milestone lengths (any order); empty disables both
            milestone fields.

    Returns:
        The streak summary (all zeros/None on an empty ledger).
    """
    days = {day for day in active_days if day <= today}
    if not days:
        first = min(milestones) if milestones else None
        return StreakSummary(current=0, longest=0, milestone_reached=None, next_milestone=first)

    longest = 0
    run = 0
    previous: date | None = None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    # Current streak: walk back from today (grace: yesterday anchors too).
    anchor = today if today in days else today - timedelta(days=1)
    current = 0
    while anchor in days:
        current += 1
        anchor -= timedelta(days=1)

    ordered = sorted(milestones)
    reached = max((m for m in ordered if m <= current), default=None)
    upcoming = next((m for m in ordered if m > current), None)
    return StreakSummary(
        current=current, longest=longest, milestone_reached=reached, next_milestone=upcoming
    )
