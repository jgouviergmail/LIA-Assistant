"""When this process started — the one "recent change" every diagnosis asks about.

Three of four stored diagnoses (2026-09-02 → 2026-09-05) recommended checking
"recent configuration or deployment changes" without being able to: nothing in
the evidence said which build was running or for how long. The stamp is taken
when :mod:`src.main` imports this module, so it dates the BOOT — a lazily
imported constant would date the first incident instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

#: Aware UTC instant this process imported the application entry point.
PROCESS_STARTED_AT: datetime = datetime.now(UTC)


def uptime_seconds() -> int:
    """Whole seconds elapsed since :data:`PROCESS_STARTED_AT` (never negative)."""
    return max(0, int((datetime.now(UTC) - PROCESS_STARTED_AT).total_seconds()))
