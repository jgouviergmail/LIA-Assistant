"""Prometheus metrics for the Personal Journals (Stratified Consciousness).

Covers:
- Lifecycle counters per action and theme.
- Extraction LLM duration.
- Effectiveness gauge: average age in days of entries that were never injected.
- Self-evaluation outcomes (evidence vs contradiction) — populated when the
  deferred self-evaluation mechanism (T → T+1) is wired up in commit 2.
- Consolidation effects — promotions between levels, dedup actions.
- Portrait compilation duration and presence per flow — wired up in commit 3.
- User feedback signal volume (levier 2) — wired up in commit 3.

All metrics are best-effort: incrementing them must never break the
extraction or consolidation pipeline.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# =============================================================================
# Lifecycle counters
# =============================================================================

journal_entries_total = Counter(
    "journal_entries_total",
    "Lifecycle actions applied to journal entries by source.",
    ["action", "theme", "source"],
    # action: create | update | delete
    # theme:  self_reflection | user_observations | ideas_analyses | learnings
    # source: conversation | consolidation | manual | user_correction
)

journal_extraction_duration_seconds = Histogram(
    "journal_extraction_duration_seconds",
    "End-to-end duration of the journal extraction LLM call.",
    ["outcome"],
    # outcome: success | parse_failed | error
    buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 30.0),
)

# =============================================================================
# Effectiveness gauge (the central quality indicator)
# =============================================================================

journal_zero_injection_age_days = Gauge(
    "journal_zero_injection_age_days",
    "Average age (in days) of active entries that have never been injected. "
    "High values signal ill-formulated directives accumulating without value. "
    "Sampled periodically — typically by the consolidation scheduler.",
    multiprocess_mode="mostrecent",
)

# =============================================================================
# Self-evaluation outcomes (deferred T → T+1, wired up in commit 2)
# =============================================================================

journal_evidence_total = Counter(
    "journal_evidence_total",
    "Deferred self-evaluation outcomes signaled by the LLM during extraction.",
    ["outcome"],
    # outcome: evidence | contradiction
)

# =============================================================================
# Consolidation effects (level transitions are wired up in commit 2)
# =============================================================================

journal_consolidation_promotions_total = Counter(
    "journal_consolidation_promotions_total",
    "Level promotions/demotions applied during consolidation.",
    ["from_level", "to_level"],
    # levels: L0 | L1 | L2 | L3
)

journal_level_distribution = Gauge(
    "journal_level_distribution",
    "Number of active entries per abstraction level. Sampled periodically.",
    ["level"],
    # level: L0 | L1 | L2 | L3
    multiprocess_mode="mostrecent",
)

journal_dedup_actions_total = Counter(
    "journal_dedup_actions_total",
    "Dedup actions performed during consolidation (merges that delete sources).",
)

# =============================================================================
# Portrait compilation and diffusion (wired up in commit 3)
# =============================================================================

journal_portrait_compile_duration_seconds = Histogram(
    "journal_portrait_compile_duration_seconds",
    "Duration of the portrait compilation step inside the consolidation LLM call.",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

journal_portrait_present_total = Counter(
    "journal_portrait_present_total",
    "Times the user model portrait was actually injected into a downstream prompt.",
    ["flow", "format"],
    # flow:   response | planner | react | interest | reminder | voice |
    #         heartbeat | fallback | briefing
    # format: full | brief
)

journal_portrait_age_hours = Gauge(
    "journal_portrait_age_hours",
    "Age (in hours) of the latest compiled portrait per user. "
    "Sampled periodically — high values signal users whose consolidation has stalled.",
    multiprocess_mode="mostrecent",
)

journal_portrait_feedback_total = Counter(
    "journal_portrait_feedback_total",
    "User-initiated feedback signals on the portrait (levier 2). "
    "Each signal triggers a synchronous re-consolidation.",
    ["outcome"],
    # outcome: success | error
)
