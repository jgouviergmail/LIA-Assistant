"""Prometheus metrics for the personal radio (ADR-324).

Counts, durations and one freshness stamp — never a word of a programme, a
listener's site or a story. Every metric here is drawn on dashboard
``31-radio.json``; the coverage ratchet refuses a blind one.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

radio_session_starts_total = Counter(
    "radio_session_starts_total",
    "Radio starts, by outcome: started, or the refusal's stable code.",
    ["outcome"],
    # outcome: started | radio_instance_full | radio_no_voice | radio_voice_unavailable
)

radio_sessions_ended_total = Counter(
    "radio_sessions_ended_total",
    "Radio sessions whose loop ended them, by reason (a worker stopping ends nothing).",
    ["reason"],
    # reason: the EndReason vocabulary (timer | listener | idle | failures | budget)
)

radio_segments_total = Counter(
    "radio_segments_total",
    "Segments a session set out to produce, by format and outcome.",
    ["format", "outcome"],
    # outcome: nothing_to_say | error (a defect) | the ProductionOutcome vocabulary
    #          (produced | writer_refused | script_refused | check_failed | voice_failed | mix_failed)
)

radio_segment_production_seconds = Histogram(
    "radio_segment_production_seconds",
    "Time to produce one aired segment (desk, writer, checks, voices, mix), by format.",
    ["format"],
    buckets=(2.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0, 120.0, 180.0),
)

radio_loop_failures_total = Counter(
    "radio_loop_failures_total",
    "Session loops that broke on a defect (the session ends as failed).",
)

radio_newsroom_passes_total = Counter(
    "radio_newsroom_passes_total",
    "Newsroom job ticks, by outcome: completed, cut (by its deadline, what it filed "
    "kept), failed, off (the radio switched off: nothing read).",
    ["outcome"],
)

# Stamped only by a tick that ran to its end, never at boot: uvicorn recycles
# workers (--limit-max-requests), and a boot stamp would hide a stalled
# newsroom. A failing pass stamps nothing, so the age covers both failures.
radio_newsroom_last_run_timestamp_seconds = Gauge(
    "radio_newsroom_last_run_timestamp_seconds",
    "When the newsroom job last ran to its end (a pass, or a tick with the radio "
    "switched off); a failed pass leaves it where it was.",
    multiprocess_mode="mostrecent",
)

radio_newsroom_feed_readings_total = Counter(
    "radio_newsroom_feed_readings_total",
    "Feeds the newsroom read, by outcome: read (answered, unchanged included) or failed.",
    ["outcome"],
)

radio_newsroom_stories_total = Counter(
    "radio_newsroom_stories_total",
    "Stories the newsroom filed or let go: new (first seen), purged (past the retention).",
    ["event"],
)

radio_newsroom_texts_total = Counter(
    "radio_newsroom_texts_total",
    "Full texts of stories, by outcome: ready, or unavailable after its last attempt.",
    ["outcome"],
)

radio_media_orphans_removed_total = Counter(
    "radio_media_orphans_removed_total",
    "Session audio directories removed by the sweep: what a crash left behind.",
)

radio_source_lookups_total = Counter(
    "radio_source_lookups_total",
    "Looking for a site's feed (a preview, or an add that looks again), by outcome.",
    ["outcome"],
    # outcome: the DiscoveryOutcome vocabulary (found, not_public, unreachable, forbidden, no_feed)
)

__all__ = [
    "radio_loop_failures_total",
    "radio_media_orphans_removed_total",
    "radio_newsroom_feed_readings_total",
    "radio_newsroom_last_run_timestamp_seconds",
    "radio_newsroom_passes_total",
    "radio_newsroom_stories_total",
    "radio_newsroom_texts_total",
    "radio_segment_production_seconds",
    "radio_segments_total",
    "radio_session_starts_total",
    "radio_sessions_ended_total",
    "radio_source_lookups_total",
]
