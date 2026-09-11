"""Pure rules over a recurring habit's offer bookkeeping (ADR-214 stop rule).

``payload.offer_dates`` holds the ISO dates the heartbeat OFFERED to run the
routine (bounded to the last five). Two readers share these rules: the
heartbeat, which decides whether one more offer is allowed, and the nightly
sync, which decides whether the mute the stop rule imposed may be lifted.
They used to live in the heartbeat alone; the sync is in the habits domain
and heartbeat already imports habits, so the rules moved here and the
heartbeat re-exports them.
"""

from __future__ import annotations

from collections.abc import Iterable


def ignored_offer_count(offer_dates: list[str], occurrence_days: Iterable[str]) -> int:
    """Consecutive trailing offers with no occurrence on the same or a later day.

    An offer counts as ignored while no occurrence happened on its day or
    after it. The offer's own day counts as an uptake because an offer is
    only ever made once today's slot was MISSED — an occurrence on that day
    can only have come after the offer (before 2026-09-11 the rule read
    « strictly after », so someone who ran the routine an hour after being
    offered it was counted as having ignored the offer). A single uptake
    resets the run — the routine re-proved itself.

    Args:
        offer_dates: ISO dates of the offers made.
        occurrence_days: ISO dates with a recorded occurrence.

    Returns:
        The length of the trailing run of ignored offers.
    """
    days = set(occurrence_days)
    ignored = 0
    for offer_iso in sorted(offer_dates, reverse=True):
        if any(day >= offer_iso for day in days):
            break
        ignored += 1
    return ignored


def occurrence_after_last_offer(offer_dates: list[str], occurrence_days: Iterable[str]) -> bool:
    """Whether the routine re-occurred since the last offer (mute lift rule).

    With no offer on record there is nothing to lift, and the answer is True
    so a caller can reset the stop rule unconditionally.

    Args:
        offer_dates: ISO dates of the offers made.
        occurrence_days: ISO dates with a recorded occurrence.

    Returns:
        True when at least one occurrence falls on the last offer's day or
        later (same-day uptake — see :func:`ignored_offer_count`).
    """
    if not offer_dates:
        return True
    last_offer = max(offer_dates)
    return any(day >= last_offer for day in occurrence_days)
