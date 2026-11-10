"""Prometheus metrics for the learned-habits subsystem (ADR-214, ADR-375).

The nightly profile job and the habit-row sync are batch work: without
metrics, a silently failing recompute would leave every profile stale and
nothing would notice until a user asked why their habits stopped updating.

All metrics are best-effort: incrementing them must never break the job.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

habit_profile_users_total = Counter(
    "habit_profile_users_total",
    "Outcome of each per-user nightly profile recompute. A sustained 'error' "
    "share means profiles are going stale; 'skipped_no_delta' is the healthy "
    "steady state for inactive accounts.",
    ["outcome"],
    # outcome: computed | skipped_no_delta | skipped_no_activity
    #          | skipped_user_disabled | error
)

habit_profile_job_seconds = Histogram(
    "habit_profile_job_seconds",
    "Wall-clock duration of one full nightly habit-profile job run.",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600),
)

user_habits_synced_total = Counter(
    "user_habits_synced_total",
    "Habit-row sync actions performed by the nightly job.",
    ["action"],
    # action: created | updated | blocked | removed
)

# ADR-375: the nightly sync owns the life of a recurring NEED (creation,
# refresh, demotion) — one counter per action, ``skipped`` when the ledger
# could not be read and the sync deliberately changed nothing.
recurring_habits_synced_total = Counter(
    "recurring_habits_synced_total",
    "Recurring-need habit sync actions performed by the nightly job.",
    ["action"],
    # action: created | updated | demoted | blocked | capped | skipped
)

# ADR-375: every move of a proposal, by kind. ``opened``, ``refreshed``,
# ``reopened`` and ``withdrawn`` are the nightly sync's; ``accepted``,
# ``dismissed`` and ``refused`` are the person's; ``held`` counts a night a
# kind could not be judged (an observation missing) and kept what was open;
# ``shown_in_chat`` counts a proposal shown under a chat answer.
habit_proposals_total = Counter(
    "habit_proposals_total",
    "Habit proposal transitions by kind: what the nightly sync opened, refreshed, "
    "reopened, withdrew or held, what the person accepted, put off or refused, and "
    "what a chat answer showed.",
    ["kind", "transition"],
)

# ADR-375: an accepted proposal whose act could not be carried out — the
# routine cap reached, a routine gone or changed, the settings changed since.
# The proposal stays open and the person is told why (``ProposalRefusal``).
habit_proposal_action_failures_total = Counter(
    "habit_proposal_action_failures_total",
    "Accepted habit proposals whose act was refused, by kind and reason.",
    ["kind", "reason"],
    # reason: routine_limit | routine_gone | routine_changed | settings_changed
)

# The deferral steps aside for an imminent appointment (2026-09-11): counted
# so an operator can see how often the rhythm yields to the calendar.
heartbeat_rhythm_escapes_total = Counter(
    "heartbeat_rhythm_escapes_total",
    "Proactive ticks the learned-rhythm deferral let through for a reason. "
    "Named for the heartbeat, which was its only emitter; since A11 (2026-09-11) "
    "the interest sweep counts here too, under its own task_type.",
    ["task_type", "reason"],
    # task_type: heartbeat | interest — the ProactiveTask.task_type values
    # reason: imminent_event
)

heartbeat_ticks_deferred_total = Counter(
    "heartbeat_ticks_deferred_total",
    "Proactive heartbeat ticks that stood aside, and why. Extended rather than "
    "duplicated when the in-meeting guard landed (ADR-281): two metrics for "
    "« this tick did not speak » would be two places to read the same thing. "
    "A sustained rhythm surge with no matching in-window deliveries would mean "
    "the anti-starvation rule is broken. Since A11 (2026-09-11) the interest sweep "
    "stands aside for the same two reasons and counts here under its task_type.",
    ["task_type", "day_class", "reason"],
    # task_type: heartbeat | interest — the ProactiveTask.task_type values
    # day_class: weekday | weekend | unknown (the in-meeting guard runs before
    #   any day classification, and inventing one would be a false label)
    # reason: rhythm | in_meeting
)

habit_window_rejected_total = Counter(
    "habit_window_rejected_total",
    "Candidate windows rejected by the rhythm detector, per gate (audit "
    "2026-08-19 lot 0). Answers 'why zero habits' from Grafana instead of an "
    "offline ledger replay: a presence/wilson-dominated census means no "
    "concentrated routine, a capture/selectivity one means activity too "
    "spread for the claimed hours to be informative.",
    ["day_class", "gate"],
    # day_class: weekday | weekend
    # gate: presence | wilson | recent | halves | capture | selectivity
)

habit_ambient_block_total = Counter(
    "habit_ambient_block_total",
    "Ambient rhythm-block presence per flow (portrait-counter precedent) — "
    "the observable trace of a prompt injection that has no debug section.",
    ["flow", "kind"],
    # kind: rhythm | unusual_hour | absence
)

habits_presence_recorded_total = Counter(
    "habits_presence_recorded_total",
    "Reading-presence signals received (ADR-214 amendment 2026-09-03): an app "
    "opening (visibility ping) or a thumb on a notification. 'banked' means an "
    "activity hour was written to the rollup; 'throttled' means that local hour "
    "was already banked; 'disabled' means the feature or the user preference is off.",
    ["kind", "outcome"],
    # kind: visibility | feedback
    # outcome: banked | throttled | disabled | error
)
