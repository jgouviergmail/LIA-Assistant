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

briefing_section_attempt_markers_total = Counter(
    "briefing_section_attempt_markers_total",
    "Attempt markers of failed briefing section reads (spec 2026-10-21, A8).",
    ["outcome"],
    # outcome: written — a live read failed and its section is settled for the
    #                     completeness readers;
    #          settled — a completeness reader took the marker instead of
    #                     rebuilding (one avoided re-read of the failing source);
    #          cleared — a later success removed it.
)

briefing_section_writes_fenced_total = Counter(
    "briefing_section_writes_fenced_total",
    "Section cache writes refused because a push invalidated the section during the read (E5).",
    ["section"],
    # section: the closed briefing section vocabulary (weather, agenda, mails, ...)
)

briefing_act_step_duration_seconds = Histogram(
    "briefing_act_step_duration_seconds",
    "Server time of each step of a progressive dashboard load (spec 2026-10-21 §5.8).",
    ["step"],
    # step: initial (the first response: cached and local sections) | section (one
    #       pending section of the act) | text (the greeting and synthesis) | refresh
    #       (one card re-read on request). A page load no longer calls the bundle
    #       build, whose duration only sees a refresh-all and external clients.
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

briefing_refresh_requests_total = Counter(
    "briefing_refresh_requests_total",
    "User-initiated refreshes: POST /briefing/refresh and a card's own refresh route.",
    ["scope"],
    # scope: single | all
)

briefing_bundle_builds_total = Counter(
    "briefing_bundle_builds_total",
    "Bundle build requests, split by whether this caller ran the build or joined one.",
    ["outcome"],
    # outcome: owned  — this caller gathered the nine sections
    #          joined — another caller was already gathering them; the work
    #                   was shared instead of repeated. One page load issues
    #                   /cards and /synthesis in parallel, so a healthy
    #                   instance shows roughly as many joins as it shows
    #                   cold or partial builds.
)

briefing_llm_invocations_total = Counter(
    "briefing_llm_invocations_total",
    "Briefing LLM invocations (greeting / synthesis).",
    ["kind", "outcome"],
    # kind: greeting | synthesis
    # outcome: success | skipped | error
)
