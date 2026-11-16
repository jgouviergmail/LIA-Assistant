"""Prometheus metrics for postponing a fired reminder (ADR-268 amendment 2026-11-16).

Two questions the snooze raises and no log answers at a glance:

- what the presses do, per surface — whether the push actions are used at all
  (a browser may not draw them), how often a press arrives too late or lands
  on a series' next occurrence;
- how many fired reminders went out WITHOUT the offer, because their
  occurrence could not be recorded (the reminder still rings: the record is
  never a gate).
"""

from __future__ import annotations

from prometheus_client import Counter

reminder_firing_actions_total = Counter(
    "reminder_firing_actions_total",
    "Presses on a fired reminder, by surface, action and outcome.",
    ["surface", "action", "outcome"],
    # surface: chat | push | telegram
    # action:  snooze | stop
    # outcome: snoozed | already_snoozed | expired | collides (snooze)
    #          stopped | already_stopped (stop)
)

reminder_firings_unrecorded_total = Counter(
    "reminder_firings_unrecorded_total",
    "Fired reminders notified without a snooze offer: their occurrence was not recorded.",
)
