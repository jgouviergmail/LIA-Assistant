"""The personal radio (ADR-324): an instance newsroom and one antenna per listener.

Contains settings for:
- The deployment ceiling of the capability (``PlatformCapability.RADIO``)
- Sessions: the automatic stop, the instance cap, the loop and its timeouts
- Production: the stage timings the look-ahead sizes itself on, the bounds of
  one segment (voices, mix, quotations, the expert analysis)
- The newsroom: how often, how much and for how long it reads; the sites a
  listener may add
- Media: where a session's audio lives and when an orphan goes

Created: 2026-09-26
Reference: docs/architecture/ADR-324-Personal-Radio.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    RADIO_AIRED_LEDGER_TTL_SECONDS_DEFAULT,
    RADIO_ANALYSIS_MAX_POINTS_DEFAULT,
    RADIO_ANALYSIS_MIN_POINTS_DEFAULT,
    RADIO_BUDGET_24H_EUR_DEFAULT,
    RADIO_COST_ESTIMATE_MIN_AUDIO_SECONDS_DEFAULT,
    RADIO_CUSTOM_SOURCES_MAX_DEFAULT,
    RADIO_DESK_TTL_SECONDS_DEFAULT,
    RADIO_FAILURES_MAX_DEFAULT,
    RADIO_FIRST_DELAY_SECONDS_DEFAULT,
    RADIO_FLASH_POLL_SECONDS_DEFAULT,
    RADIO_IDLE_TIMEOUT_SECONDS_DEFAULT,
    RADIO_INTEREST_FRESH_SECONDS_DEFAULT,
    RADIO_INTEREST_STORIES_MAX_DEFAULT,
    RADIO_INTEREST_TOPICS_MAX_DEFAULT,
    RADIO_LOOKAHEAD_MARGIN_SECONDS_DEFAULT,
    RADIO_LOOKAHEAD_SAFETY_DEFAULT,
    RADIO_LOOP_LEASE_SECONDS_DEFAULT,
    RADIO_LOOP_TICK_SECONDS_DEFAULT,
    RADIO_MAX_ACTIVE_SESSIONS_DEFAULT,
    RADIO_MEDIA_ORPHAN_AGE_SECONDS_DEFAULT,
    RADIO_MEDIA_SWEEP_INTERVAL_SECONDS_DEFAULT,
    RADIO_MIX_TIMEOUT_SECONDS_DEFAULT,
    RADIO_NEWSROOM_BACKOFF_MAX_SECONDS_DEFAULT,
    RADIO_NEWSROOM_CONCURRENCY_DEFAULT,
    RADIO_NEWSROOM_FEED_INTERVAL_SECONDS_DEFAULT,
    RADIO_NEWSROOM_FEED_MAX_BYTES_DEFAULT,
    RADIO_NEWSROOM_FEEDS_PER_PASS_DEFAULT,
    RADIO_NEWSROOM_INTERVAL_SECONDS_DEFAULT,
    RADIO_NEWSROOM_LISTENER_WINDOW_SECONDS_DEFAULT,
    RADIO_NEWSROOM_PAGE_MAX_BYTES_DEFAULT,
    RADIO_NEWSROOM_PASS_TIMEOUT_SECONDS_DEFAULT,
    RADIO_NEWSROOM_RETENTION_SECONDS_DEFAULT,
    RADIO_NEWSROOM_TEXT_ATTEMPTS_MAX_DEFAULT,
    RADIO_NEWSROOM_TEXTS_PER_PASS_DEFAULT,
    RADIO_PAUSE_TIMEOUT_SECONDS_DEFAULT,
    RADIO_QUOTE_MAX_CHARS_DEFAULT,
    RADIO_RECORD_TTL_SECONDS_DEFAULT,
    RADIO_SAME_EVENT_SIMILARITY_DEFAULT,
    RADIO_SEGMENT_GAP_SECONDS_DEFAULT,
    RADIO_SOURCE_PREVIEW_RATE_LIMIT_CALLS_DEFAULT,
    RADIO_SOURCE_PREVIEW_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    RADIO_STAGE_ANALYSIS_SECONDS_DEFAULT,
    RADIO_STAGE_MIX_SECONDS_DEFAULT,
    RADIO_STAGE_WRITER_SECONDS_DEFAULT,
    RADIO_STORAGE_PATH_DEFAULT,
    RADIO_TIMER_MAX_MINUTES_DEFAULT,
    RADIO_TIMER_MINUTES_DEFAULT,
    RADIO_TTS_CONCURRENCY_DEFAULT,
    RADIO_TTS_LINE_ATTEMPTS_DEFAULT,
    RADIO_TTS_RATE_LIMIT_WAIT_MAX_SECONDS_DEFAULT,
    RADIO_TTS_REALTIME_FACTOR_DEFAULT,
    RADIO_VERIFICATION_DEFAULT,
)


class RadioSettings(BaseSettings):
    """Settings of the personal radio."""

    radio_enabled: bool = Field(
        default=True,
        description=(
            "Deployment ceiling for the personal radio (PlatformCapability.RADIO): the "
            "routes, the header control, the newsroom collector and every session."
        ),
    )

    # --- Sessions --------------------------------------------------------------
    radio_timer_minutes: int = Field(
        default=RADIO_TIMER_MINUTES_DEFAULT,
        ge=5,
        le=240,
        description="The automatic stop of a session whose listener chose none (minutes).",
    )
    radio_timer_max_minutes: int = Field(
        default=RADIO_TIMER_MAX_MINUTES_DEFAULT,
        ge=5,
        le=480,
        description="The longest automatic stop a listener may choose (minutes, published).",
    )
    radio_max_active_sessions: int = Field(
        default=RADIO_MAX_ACTIVE_SESSIONS_DEFAULT,
        ge=1,
        le=1_000,
        description="Sessions the instance runs at once; a start past it is refused.",
    )
    radio_budget_24h_eur: float = Field(
        default=RADIO_BUDGET_24H_EUR_DEFAULT,
        ge=0.0,
        le=1_000.0,
        description=(
            "What one listener's radio may spend over a rolling 24 hours, sessions and "
            "article translations (EUR, published; 0 = no bound)."
        ),
    )
    radio_record_ttl_seconds: int = Field(
        default=RADIO_RECORD_TTL_SECONDS_DEFAULT,
        ge=300,
        le=86_400,
        description="How long a session's Redis keys outlive their last write (seconds).",
    )
    radio_loop_lease_seconds: int = Field(
        default=RADIO_LOOP_LEASE_SECONDS_DEFAULT,
        ge=10,
        le=600,
        description="The lease of the worker driving a session, renewed every tick (seconds).",
    )
    radio_loop_tick_seconds: float = Field(
        default=RADIO_LOOP_TICK_SECONDS_DEFAULT,
        ge=0.5,
        le=10.0,
        description="How often a session's loop reads the player and decides (seconds).",
    )
    radio_first_delay_seconds: float = Field(
        default=RADIO_FIRST_DELAY_SECONDS_DEFAULT,
        ge=5.0,
        le=120.0,
        description="The station's music before the first segment, at most (seconds).",
    )
    radio_desk_ttl_seconds: int = Field(
        default=RADIO_DESK_TTL_SECONDS_DEFAULT,
        ge=30,
        le=3_600,
        description="How long the listener's day and the news desk stay read (seconds).",
    )
    radio_flash_poll_seconds: float = Field(
        default=RADIO_FLASH_POLL_SECONDS_DEFAULT,
        ge=5.0,
        le=300.0,
        description="How often a session looks for what LIA just wrote to the listener — a news flash's delay (seconds).",
    )
    radio_idle_timeout_seconds: int = Field(
        default=RADIO_IDLE_TIMEOUT_SECONDS_DEFAULT,
        ge=15,
        le=900,
        description="No report from the player for this long ends the session (seconds).",
    )
    radio_pause_timeout_seconds: int = Field(
        default=RADIO_PAUSE_TIMEOUT_SECONDS_DEFAULT,
        ge=60,
        le=7_200,
        description="A pause this long ends the session (seconds).",
    )
    radio_failures_max: int = Field(
        default=RADIO_FAILURES_MAX_DEFAULT,
        ge=1,
        le=20,
        description="Productions failing in a row before the session ends.",
    )
    radio_lookahead_safety: float = Field(
        default=RADIO_LOOKAHEAD_SAFETY_DEFAULT,
        ge=1.0,
        le=5.0,
        description="Factor on a production's expected time when deciding to start it.",
    )
    radio_lookahead_margin_seconds: float = Field(
        default=RADIO_LOOKAHEAD_MARGIN_SECONDS_DEFAULT,
        ge=0.0,
        le=300.0,
        description="Seconds added on top of the look-ahead.",
    )
    radio_aired_ledger_ttl_seconds: int = Field(
        default=RADIO_AIRED_LEDGER_TTL_SECONDS_DEFAULT,
        ge=3_600,
        le=7 * 86_400,
        description="How long a listener's programmes remember what they aired (seconds).",
    )
    radio_interest_topics_max: int = Field(
        default=RADIO_INTEREST_TOPICS_MAX_DEFAULT,
        ge=0,
        le=8,
        description=(
            "The listener's strongest interests a session reads when it starts: the ones "
            "the writer is told and those searched for stories with their own search key "
            "(0 = none)."
        ),
    )
    radio_interest_stories_max: int = Field(
        default=RADIO_INTEREST_STORIES_MAX_DEFAULT,
        ge=1,
        le=20,
        description="The stories one interest's search keeps.",
    )
    radio_interest_fresh_seconds: int = Field(
        default=RADIO_INTEREST_FRESH_SECONDS_DEFAULT,
        ge=600,
        le=2 * 86_400,
        description=(
            "An interest searched within this window is not searched again: a session "
            "reuses what the last search found (seconds)."
        ),
    )
    radio_same_event_similarity: float = Field(
        default=RADIO_SAME_EVENT_SIMILARITY_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "Two headlines at least this close in meaning tell one event: once one is "
            "heard, the others stay unsaid (0 = the words alone judge; no embedding)."
        ),
    )

    # --- Production ------------------------------------------------------------
    radio_stage_writer_seconds: float = Field(
        default=RADIO_STAGE_WRITER_SECONDS_DEFAULT,
        gt=0.0,
        le=120.0,
        description=(
            "Expected time of one writer call (look-ahead; a session adds what its own "
            "productions overran)."
        ),
    )
    radio_stage_analysis_seconds: float = Field(
        default=RADIO_STAGE_ANALYSIS_SECONDS_DEFAULT,
        gt=0.0,
        le=120.0,
        description="Expected time of one analyst call.",
    )
    radio_tts_realtime_factor: float = Field(
        default=RADIO_TTS_REALTIME_FACTOR_DEFAULT,
        gt=0.0,
        le=5.0,
        description="Seconds of synthesis per second of audio, one line at a time.",
    )
    radio_tts_concurrency: int = Field(
        default=RADIO_TTS_CONCURRENCY_DEFAULT,
        ge=1,
        le=16,
        description="Lines of one segment voiced at once.",
    )
    radio_tts_line_attempts: int = Field(
        default=RADIO_TTS_LINE_ATTEMPTS_DEFAULT,
        ge=1,
        le=5,
        description="Attempts per line while its voice failure is transient.",
    )
    radio_cost_estimate_min_audio_seconds: int = Field(
        default=RADIO_COST_ESTIMATE_MIN_AUDIO_SECONDS_DEFAULT,
        ge=30,
        le=1800,
        description=(
            "Seconds of radio produced before a session's cost is extrapolated to its "
            "planned listening (the estimate beside the cost); too short, the estimate "
            "swings with the first programmes; too long, it comes late."
        ),
    )
    radio_tts_rate_limit_wait_max_seconds: int = Field(
        default=RADIO_TTS_RATE_LIMIT_WAIT_MAX_SECONDS_DEFAULT,
        ge=1,
        le=120,
        description=(
            "Longest wait a voice line accepts after a provider's rate limit (the "
            "provider's own delay when it names one, bounded by this)."
        ),
    )
    radio_stage_mix_seconds: float = Field(
        default=RADIO_STAGE_MIX_SECONDS_DEFAULT,
        gt=0.0,
        le=60.0,
        description="Expected time of one mix.",
    )
    radio_segment_gap_seconds: float = Field(
        default=RADIO_SEGMENT_GAP_SECONDS_DEFAULT,
        ge=0.0,
        le=30.0,
        description=(
            "Seconds of the station's music between two programmes (0: none), fixed in a "
            "session when it starts: the player waits as long, and fewer programmes are "
            "produced over a long listening."
        ),
    )
    radio_mix_timeout_seconds: int = Field(
        default=RADIO_MIX_TIMEOUT_SECONDS_DEFAULT,
        ge=10,
        le=600,
        description="The mix's deadline (seconds).",
    )
    radio_analysis_min_points: int = Field(
        default=RADIO_ANALYSIS_MIN_POINTS_DEFAULT,
        ge=1,
        le=12,
        description="Points the expert analysis must hold to air.",
    )
    radio_analysis_max_points: int = Field(
        default=RADIO_ANALYSIS_MAX_POINTS_DEFAULT,
        ge=1,
        le=12,
        description="Points of the expert analysis kept, the analyst's order.",
    )
    radio_quote_max_chars: int = Field(
        default=RADIO_QUOTE_MAX_CHARS_DEFAULT,
        ge=20,
        le=500,
        description="The longest verbatim quotation a segment may air (fair use).",
    )
    radio_verification_default: Literal["off", "news", "all"] = Field(
        default=RADIO_VERIFICATION_DEFAULT,
        description="The model verifier's reach for a listener who chose none.",
    )

    # --- Newsroom ----------------------------------------------------------------
    radio_newsroom_interval_seconds: int = Field(
        default=RADIO_NEWSROOM_INTERVAL_SECONDS_DEFAULT,
        ge=60,
        le=3_600,
        description="How often the collector job runs (seconds).",
    )
    radio_newsroom_feeds_per_pass: int = Field(
        default=RADIO_NEWSROOM_FEEDS_PER_PASS_DEFAULT,
        ge=1,
        le=500,
        description="Due feeds read by one pass.",
    )
    radio_newsroom_texts_per_pass: int = Field(
        default=RADIO_NEWSROOM_TEXTS_PER_PASS_DEFAULT,
        ge=0,
        le=500,
        description="Full texts fetched by one pass.",
    )
    radio_newsroom_feed_interval_seconds: int = Field(
        default=RADIO_NEWSROOM_FEED_INTERVAL_SECONDS_DEFAULT,
        ge=300,
        le=86_400,
        description="A feed is read again after this long (seconds).",
    )
    radio_newsroom_backoff_max_seconds: int = Field(
        default=RADIO_NEWSROOM_BACKOFF_MAX_SECONDS_DEFAULT,
        ge=600,
        le=7 * 86_400,
        description="The longest a failing feed is left alone (seconds).",
    )
    radio_newsroom_feed_max_bytes: int = Field(
        default=RADIO_NEWSROOM_FEED_MAX_BYTES_DEFAULT,
        ge=64 * 1024,
        le=32 * 1024 * 1024,
        description="The largest feed body read (decoded bytes).",
    )
    radio_newsroom_page_max_bytes: int = Field(
        default=RADIO_NEWSROOM_PAGE_MAX_BYTES_DEFAULT,
        ge=64 * 1024,
        le=32 * 1024 * 1024,
        description="The largest article page read (decoded bytes).",
    )
    radio_newsroom_text_attempts_max: int = Field(
        default=RADIO_NEWSROOM_TEXT_ATTEMPTS_MAX_DEFAULT,
        ge=1,
        le=10,
        description="Attempts at an article's full text before it stays summary-only.",
    )
    radio_newsroom_retention_seconds: int = Field(
        default=RADIO_NEWSROOM_RETENTION_SECONDS_DEFAULT,
        ge=6 * 3_600,
        le=30 * 86_400,
        description="How long a stored story is kept (seconds).",
    )
    radio_newsroom_listener_window_seconds: int = Field(
        default=RADIO_NEWSROOM_LISTENER_WINDOW_SECONDS_DEFAULT,
        ge=3_600,
        le=90 * 86_400,
        description=(
            "The newsroom reads the catalogue while anyone started a session within this "
            "window, and a listener's own sites while they did (seconds)."
        ),
    )
    radio_newsroom_concurrency: int = Field(
        default=RADIO_NEWSROOM_CONCURRENCY_DEFAULT,
        ge=1,
        le=32,
        description="Outlets read at once (one outlet's articles in series).",
    )
    radio_newsroom_pass_timeout_seconds: int = Field(
        default=RADIO_NEWSROOM_PASS_TIMEOUT_SECONDS_DEFAULT,
        ge=30,
        le=3_600,
        description="The deadline of one collector pass (under the job's interval).",
    )
    radio_custom_sources_max: int = Field(
        default=RADIO_CUSTOM_SOURCES_MAX_DEFAULT,
        ge=0,
        le=100,
        description="Sites one listener may add to their newsroom (published).",
    )
    radio_source_preview_rate_limit_calls: int = Field(
        default=RADIO_SOURCE_PREVIEW_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1_000,
        description="Site lookups (preview and add) one account may ask per window.",
    )
    radio_source_preview_rate_limit_window_seconds: int = Field(
        default=RADIO_SOURCE_PREVIEW_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=86_400,
        description="The sliding window of the source lookup limit (seconds).",
    )

    # --- Media ----------------------------------------------------------------------
    radio_storage_path: str = Field(
        default=RADIO_STORAGE_PATH_DEFAULT,
        description="Where a session's audio lives while it airs (one directory per session).",
    )
    radio_media_orphan_age_seconds: int = Field(
        default=RADIO_MEDIA_ORPHAN_AGE_SECONDS_DEFAULT,
        ge=300,
        le=86_400,
        description="A session directory with no live session behind it goes after this long.",
    )
    radio_media_sweep_interval_seconds: int = Field(
        default=RADIO_MEDIA_SWEEP_INTERVAL_SECONDS_DEFAULT,
        ge=60,
        le=86_400,
        description="How often the orphan sweep runs (seconds).",
    )

    @model_validator(mode="after")
    def _coherent(self) -> RadioSettings:
        """Refuse bounds that contradict each other (the boot fails, never the session)."""
        if self.radio_timer_minutes > self.radio_timer_max_minutes:
            raise ValueError("RADIO_TIMER_MINUTES exceeds RADIO_TIMER_MAX_MINUTES")
        if self.radio_analysis_min_points > self.radio_analysis_max_points:
            raise ValueError("RADIO_ANALYSIS_MIN_POINTS exceeds RADIO_ANALYSIS_MAX_POINTS")
        if self.radio_newsroom_pass_timeout_seconds >= self.radio_newsroom_interval_seconds:
            raise ValueError("a newsroom pass must end before the next one starts")
        if self.radio_record_ttl_seconds <= self.radio_pause_timeout_seconds:
            raise ValueError("a paused session's keys must outlive its pause timeout")
        return self
