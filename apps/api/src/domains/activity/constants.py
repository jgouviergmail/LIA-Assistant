"""Activity domain constants — event kinds of the proactive timeline.

Kinds are stable API identifiers: the frontend resolves each to a
localized label (``label_key`` doctrine). Reminders are deliberately
absent — delivered reminders leave no persisted row (ephemeral), and a
count without a trace would be a claim we cannot honor (ADR-185).
"""

from __future__ import annotations

ACTIVITY_KIND_HEARTBEAT_NOTIFICATION = "heartbeat_notification"
ACTIVITY_KIND_INTEREST_NOTIFICATION = "interest_notification"
ACTIVITY_KIND_JOURNAL_ENTRY = "journal_entry"
ACTIVITY_KIND_HABIT_DETECTED = "habit_detected"
ACTIVITY_KIND_OPEN_LOOP_CREATED = "open_loop_created"
ACTIVITY_KIND_OPEN_LOOP_CLOSED = "open_loop_closed"
ACTIVITY_KIND_SCHEDULED_ACTION_RUN = "scheduled_action_run"

ALL_ACTIVITY_KINDS: tuple[str, ...] = (
    ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,
    ACTIVITY_KIND_INTEREST_NOTIFICATION,
    ACTIVITY_KIND_JOURNAL_ENTRY,
    ACTIVITY_KIND_HABIT_DETECTED,
    ACTIVITY_KIND_OPEN_LOOP_CREATED,
    ACTIVITY_KIND_OPEN_LOOP_CLOSED,
    ACTIVITY_KIND_SCHEDULED_ACTION_RUN,
)

# Journal sources surfaced on the timeline: automatic extractions only.
# Manual entries and user corrections are the USER's actions, not LIA's.
TIMELINE_JOURNAL_SOURCES: tuple[str, ...] = ("conversation", "consolidation")
