"""Jitter for interval jobs — one implementation, imported by every registrar.

Periodic jobs that share a divisor align forever (measured 2026-09-01: six jobs
in one second, hourly). Every ``IntervalTrigger`` carries a jitter derived from
its own period through this helper, so the spread scales with the cadence. It
lives in its own module so a per-domain registrar (``scheduler_meetings``) can
import it without importing the startup step that imports THEM.
"""

from __future__ import annotations

#: Share of a job's period used as its random spread.
#:
#: Small enough that a job stays recognisably "every five minutes", wide enough
#: that two jobs sharing a period stop landing on the same second.
_JITTER_RATIO = 0.15

#: Floor, in seconds. A percentage of a short period rounds to zero, which would
#: leave the FASTEST jobs perfectly aligned — precisely the ones that collide
#: most often.
_JITTER_FLOOR_SECONDS = 5


def jitter_seconds_for(*, hours: float = 0, minutes: float = 0, seconds: float = 0) -> int:
    """Random spread to give an interval job of this period.

    Interval triggers all start counting at scheduler start, so periods that
    share a divisor align forever. Measured in production on 2026-09-01: the
    periods were 5, 5, 15, 30, 30 and 60 minutes, and six jobs fired inside the
    same second every hour — each one running an agent, each agent issuing
    several embeddings, against a provider quota that tolerates the volume but
    not the concentration.

    Args:
        hours: Period in hours.
        minutes: Period in minutes; added to ``hours``.
        seconds: Period in seconds; added to the rest.

    Returns:
        Seconds of jitter, always strictly under the period so two consecutive
        runs can neither overlap nor invert. Zero for a non-positive period —
        startup must not fail on arithmetic, and a bad interval is already the
        settings layer's job to report.
    """
    period = hours * 3600 + minutes * 60 + seconds
    if period <= 0:
        return 0
    spread = max(_JITTER_FLOOR_SECONDS, int(period * _JITTER_RATIO))
    # Never reach the period itself: at equality a run could land on the next.
    return min(spread, max(1, int(period) - 1))
