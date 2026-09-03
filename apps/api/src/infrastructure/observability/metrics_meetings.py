"""Prometheus metrics for meeting recording & structured minutes (ADR-258).

Covers the whole life of a meeting: recordings started and finished by
status, recorded duration, segments received by format, processing time by
stage, failures by reason, reaper transitions, and the audio seconds each
transcription engine consumed (the cost driver). Every metric here is wired
to the ``27 - Meetings`` dashboard — the coverage ratchet refuses a blind one.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

meetings_total = Counter(
    "meetings_total",
    "Meetings that reached a terminal or resting state, by status.",
    ["status"],
    # status: ready | failed | discarded
)

meeting_recording_duration_seconds = Histogram(
    "meeting_recording_duration_seconds",
    "Recorded audio duration of processed meetings, in seconds.",
    buckets=(60.0, 300.0, 900.0, 1800.0, 3600.0, 5400.0, 7200.0, 10800.0),
)

meeting_segments_received_total = Counter(
    "meeting_segments_received_total",
    "Audio segments accepted by the API, by client format.",
    ["format"],
    # format: pcm_s16le_16 | webm_opus | ogg_opus
)

meeting_processing_stage_duration_seconds = Histogram(
    "meeting_processing_stage_duration_seconds",
    "Wall-clock time of one processing stage.",
    ["stage"],
    # stage: normalizing | transcribing | synthesizing | indexing
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 900.0, 1800.0),
)

meeting_failures_total = Counter(
    "meeting_failures_total",
    "Processing failures by reason code (transient retries included).",
    ["reason"],
    # reason: usage_limit | no_engine | invalid_api_key | provider_error |
    #         no_speech | transcript_too_long | synthesis_error | indexing_error |
    #         normalize_error | storage_error
)

meeting_reaper_transitions_total = Counter(
    "meeting_reaper_transitions_total",
    "State transitions applied by the reapers.",
    ["outcome"],
    # outcome: interrupted | requeued | redriven | audio_purged
)

meeting_stt_audio_seconds_total = Counter(
    "meeting_stt_audio_seconds_total",
    "Audio seconds transcribed, by engine (the cost driver for remote engines).",
    ["provider"],
    # provider: elevenlabs | openai | local
)
