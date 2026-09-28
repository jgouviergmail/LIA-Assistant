"""The radio's settings, as the pure modules take them (ADR-324).

One reading of ``RadioSettings`` per shape the pure modules declare — the
start's defaults, a production's bounds, the loop's timings, the newsroom's
limits — so the start, the loop, the routes and the collector cannot read one
setting two ways. Read at call time: a setting an operator changes reaches the
next session without a restart of anything but the process that reads it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from src.core.config import settings
from src.domains.radio.newsroom.collector import CollectorLimits
from src.domains.radio.orchestrator import LoopTuning
from src.domains.radio.pacing import StageTimings
from src.domains.radio.production import ProductionLimits
from src.domains.radio.runner import RunnerSettings
from src.domains.radio.service import RadioRuntime
from src.domains.radio.session import SessionRules
from src.domains.radio.setup import VerificationMode
from src.domains.radio.setup_builder import InstanceDefaults

#: A live session publishes at every report; one silent for this many idle
#: timeouts has lost its worker, and holds no place under the instance's cap.
LIVE_HORIZON_IDLE_TIMEOUTS: Final[float] = 2.0


def radio_media_root() -> Path:
    """Where the sessions' audio lies while they air."""
    return Path(settings.radio_storage_path)


def stage_timings() -> StageTimings:
    """The stage timings the look-ahead and the startup estimate size themselves on."""
    return StageTimings(
        writer_s=settings.radio_stage_writer_seconds,
        analysis_s=settings.radio_stage_analysis_seconds,
        tts_realtime_factor=settings.radio_tts_realtime_factor,
        tts_concurrency=settings.radio_tts_concurrency,
        mix_s=settings.radio_stage_mix_seconds,
    )


def instance_defaults() -> InstanceDefaults:
    """What a listener who never chose gets."""
    return InstanceDefaults(
        timer_minutes=settings.radio_timer_minutes,
        timer_max_minutes=settings.radio_timer_max_minutes,
        verification=VerificationMode(settings.radio_verification_default),
        timings=stage_timings(),
    )


def production_limits() -> ProductionLimits:
    """The bounds of one production."""
    return ProductionLimits(
        quote_max_chars=settings.radio_quote_max_chars,
        tts_concurrency=settings.radio_tts_concurrency,
        mix_timeout_s=float(settings.radio_mix_timeout_seconds),
        tts_attempts=settings.radio_tts_line_attempts,
        tts_rate_limit_wait_max_s=float(settings.radio_tts_rate_limit_wait_max_seconds),
    )


def session_rules() -> SessionRules:
    """The bounds a session runs under."""
    return SessionRules(
        idle_timeout_s=float(settings.radio_idle_timeout_seconds),
        pause_timeout_s=float(settings.radio_pause_timeout_seconds),
        failures_max=settings.radio_failures_max,
        lookahead_safety=settings.radio_lookahead_safety,
        lookahead_margin_s=settings.radio_lookahead_margin_seconds,
    )


def runner_settings() -> RunnerSettings:
    """The loops' settings."""
    return RunnerSettings(
        media_root=radio_media_root(),
        record_ttl_s=settings.radio_record_ttl_seconds,
        lease_s=settings.radio_loop_lease_seconds,
        tuning=LoopTuning(
            tick_s=settings.radio_loop_tick_seconds,
            first_delay_s=settings.radio_first_delay_seconds,
            timings=stage_timings(),
            rules=session_rules(),
            flash_poll_s=settings.radio_flash_poll_seconds,
        ),
    )


def radio_runtime() -> RadioRuntime:
    """The session doors' settings."""
    return RadioRuntime(
        media_root=radio_media_root(),
        record_ttl_s=settings.radio_record_ttl_seconds,
        max_active_sessions=settings.radio_max_active_sessions,
        live_horizon_s=settings.radio_idle_timeout_seconds * LIVE_HORIZON_IDLE_TIMEOUTS,
        cost_estimate_min_audio_s=float(settings.radio_cost_estimate_min_audio_seconds),
        segment_gap_s=settings.radio_segment_gap_seconds,
    )


def collector_limits() -> CollectorLimits:
    """The bounds of one newsroom pass."""
    return CollectorLimits(
        feeds_per_pass=settings.radio_newsroom_feeds_per_pass,
        texts_per_pass=settings.radio_newsroom_texts_per_pass,
        feed_interval_s=float(settings.radio_newsroom_feed_interval_seconds),
        backoff_max_s=float(settings.radio_newsroom_backoff_max_seconds),
        feed_max_bytes=settings.radio_newsroom_feed_max_bytes,
        page_max_bytes=settings.radio_newsroom_page_max_bytes,
        text_attempts_max=settings.radio_newsroom_text_attempts_max,
        retention_s=float(settings.radio_newsroom_retention_seconds),
        concurrency=settings.radio_newsroom_concurrency,
        pass_timeout_s=float(settings.radio_newsroom_pass_timeout_seconds),
        listener_window_s=float(settings.radio_newsroom_listener_window_seconds),
    )


__all__ = [
    "LIVE_HORIZON_IDLE_TIMEOUTS",
    "collector_limits",
    "instance_defaults",
    "production_limits",
    "radio_media_root",
    "radio_runtime",
    "runner_settings",
    "session_rules",
    "stage_timings",
]
