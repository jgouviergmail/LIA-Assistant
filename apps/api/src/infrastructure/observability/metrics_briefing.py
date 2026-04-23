"""Prometheus metrics for the Today briefing dashboard.

Covers:
- Build duration end-to-end (cache_state label distinguishes cold/warm/partial).
- Per-section status outcomes (with origin: cache | live).
- User-initiated refresh requests (single section vs. all).
- LLM invocations (greeting / synthesis) — token tracking is delegated to
  ``track_proactive_tokens`` (see ``infrastructure/proactive/tracking.py``)
  which feeds ``message_token_summary`` + ``user_statistics`` already.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

briefing_build_duration_seconds = Histogram(
    "briefing_build_duration_seconds",
    "End-to-end time to build the Today briefing (parallel fetchers + LLM).",
    ["cache_state"],
    # cache_state: cold (all sections fetched live) | warm (all from cache)
    #            | partial (mix)
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

briefing_section_status_total = Counter(
    "briefing_section_status_total",
    "Per-section build outcomes for the Today briefing.",
    ["section", "status", "origin"],
    # section: weather | agenda | mails | birthdays | reminders | health
    # status:  ok | empty | error | not_configured
    # origin:  live | cache
)

briefing_refresh_requests_total = Counter(
    "briefing_refresh_requests_total",
    "User-initiated POST /briefing/refresh requests.",
    ["scope"],
    # scope: single | all
)

briefing_llm_invocations_total = Counter(
    "briefing_llm_invocations_total",
    "Briefing LLM invocations (greeting / synthesis).",
    ["kind", "outcome"],
    # kind: greeting | synthesis
    # outcome: success | skipped | error
)
