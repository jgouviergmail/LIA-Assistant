"""Prometheus metrics of the routines another system starts with a signed call (ADR-386).

Plotted on the « Routines started by a call » row of the proactive dashboard
(``13-proactive-heartbeat.json``). Labels are bounded vocabularies: never a
routine, an address, a sender or a body.
"""

from __future__ import annotations

from prometheus_client import Counter

routine_webhook_calls_total = Counter(
    "routine_webhook_calls_total",
    "Calls to a routine's address by what they became (ADR-386): accepted, "
    "duplicate (a delivery already accepted, answered as such), unknown (no "
    "webhook routine at the address, or a paused one), bad_signature, "
    "rate_limited (the address's own window), full (as many calls waiting as a "
    "routine may keep), too_large (refused before it was read).",
    ["outcome"],
)

routine_webhook_calls_served_total = Counter(
    "routine_webhook_calls_served_total",
    "Accepted calls a run of their routine read and answered (ADR-386). "
    "Accepted minus served, over a day, is what waits or was dropped with its "
    "routine: a growing gap is a routine whose runs fail or stand aside.",
)

__all__ = ["routine_webhook_calls_served_total", "routine_webhook_calls_total"]
