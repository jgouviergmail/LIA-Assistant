"""Meetings settings (meeting recording & structured minutes, ADR-258).

Deployment-wide knobs only. What a USER chooses (transcription engine
preference, kept audio, auto-email, minutes template) lives in the
``meeting_preferences`` / ``meeting_templates`` tables; what an ADMIN switches
at runtime (the capability) lives in the settings store. Every bound enforced
by the API is published to the client at start time (ADR-184 doctrine).

See docs/superpowers/specs/2026-09-02-meeting-recording-and-minutes-design.md.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    MEETINGS_AUDIO_RETENTION_HOURS_MAX_DEFAULT,
    MEETINGS_ENABLED_DEFAULT,
    MEETINGS_JOB_HEARTBEAT_INTERVAL_SECONDS_DEFAULT,
    MEETINGS_JOB_LEASE_TTL_SECONDS_DEFAULT,
    MEETINGS_JOB_MAX_ATTEMPTS_DEFAULT,
    MEETINGS_LOCAL_RTF_ESTIMATE_DEFAULT,
    MEETINGS_MAX_DURATION_MINUTES_CEILING,
    MEETINGS_MAX_DURATION_MINUTES_DEFAULT,
    MEETINGS_RATE_LIMIT_STARTS_DEFAULT,
    MEETINGS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    MEETINGS_REAPER_INTERVAL_SECONDS_DEFAULT,
    MEETINGS_RECORDING_STALE_MINUTES_DEFAULT,
    MEETINGS_RETENTION_REAPER_INTERVAL_MINUTES_DEFAULT,
    MEETINGS_SEGMENT_MAX_SECONDS_DEFAULT,
    MEETINGS_SEGMENT_SECONDS_DEFAULT,
    MEETINGS_SILENCE_PROMPT_MINUTES_DEFAULT,
    MEETINGS_STORAGE_PATH_DEFAULT,
    MEETINGS_STT_TIMEOUT_SECONDS_DEFAULT,
    STT_BYTES_PER_SECOND_AT_16KHZ_INT16,
)


class MeetingsSettings(BaseSettings):
    """Meeting recording & minutes settings (composed into ``Settings``)."""

    meetings_enabled: bool = Field(
        default=MEETINGS_ENABLED_DEFAULT,
        description=(
            "Master switch for meeting recording and structured minutes. When "
            "false the router is not mounted, the reapers are not scheduled and "
            "the composer never offers the recording action."
        ),
    )

    meetings_storage_path: str = Field(
        default=MEETINGS_STORAGE_PATH_DEFAULT,
        description="Root directory for meeting audio (segments, normalized file).",
    )

    meetings_max_duration_minutes: int = Field(
        default=MEETINGS_MAX_DURATION_MINUTES_DEFAULT,
        ge=5,
        le=MEETINGS_MAX_DURATION_MINUTES_CEILING,
        description=(
            "Maximum recording length; the server refuses segments beyond it and "
            "the client stops. Bounded by the remote transcription file cap (25 MB "
            "at the Opus floor), so a whole meeting always travels as ONE file and "
            "speaker labels stay consistent."
        ),
    )

    meetings_segment_seconds: int = Field(
        default=MEETINGS_SEGMENT_SECONDS_DEFAULT,
        ge=5,
        le=120,
        description=(
            "Cadence at which the client uploads a segment — also the bound on what "
            "a crash can lose. Published to the client at start."
        ),
    )

    meetings_segment_max_seconds: int = Field(
        default=MEETINGS_SEGMENT_MAX_SECONDS_DEFAULT,
        ge=5,
        le=300,
        description="Longest single segment the server accepts (client bug or abuse guard).",
    )

    meetings_recording_stale_minutes: int = Field(
        default=MEETINGS_RECORDING_STALE_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description=(
            "A recording with no segment for this long is marked interrupted; the "
            "next segment resumes it, the user may finalize or discard it."
        ),
    )

    meetings_silence_prompt_minutes: int = Field(
        default=MEETINGS_SILENCE_PROMPT_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description=(
            "Client-side silence watchdog: after this long without speech the "
            "recorder asks whether the meeting is still going. Published at start."
        ),
    )

    meetings_job_lease_ttl_seconds: int = Field(
        default=MEETINGS_JOB_LEASE_TTL_SECONDS_DEFAULT,
        ge=60,
        le=21600,
        description=(
            "How long a worker's claim on a processing job stays valid before the "
            "reaper may requeue it. Must exceed the slowest single stage."
        ),
    )

    meetings_job_heartbeat_interval_seconds: int = Field(
        default=MEETINGS_JOB_HEARTBEAT_INTERVAL_SECONDS_DEFAULT,
        ge=5,
        le=3600,
        description=(
            "How often a working job renews its lease. MUST be strictly less than "
            "meetings_job_lease_ttl_seconds (enforced)."
        ),
    )

    meetings_job_max_attempts: int = Field(
        default=MEETINGS_JOB_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=20,
        description="Bounded retry: after this many attempts a meeting is marked failed.",
    )

    meetings_reaper_interval_seconds: int = Field(
        default=MEETINGS_REAPER_INTERVAL_SECONDS_DEFAULT,
        ge=15,
        le=3600,
        description="How often the reaper scans stale recordings and stuck jobs.",
    )

    meetings_retention_reaper_interval_minutes: int = Field(
        default=MEETINGS_RETENTION_REAPER_INTERVAL_MINUTES_DEFAULT,
        ge=5,
        le=1440,
        description="How often kept audio past its retention is purged.",
    )

    meetings_audio_retention_hours_max: int = Field(
        default=MEETINGS_AUDIO_RETENTION_HOURS_MAX_DEFAULT,
        ge=1,
        le=8760,
        description=(
            "Admin ceiling on how long a user may keep the audio of a processed "
            "meeting. 0 hours is always allowed (delete after processing)."
        ),
    )

    meetings_stt_timeout_seconds: float = Field(
        default=MEETINGS_STT_TIMEOUT_SECONDS_DEFAULT,
        ge=30.0,
        le=3600.0,
        description="HTTP timeout of one remote transcription call for a whole meeting.",
    )

    meetings_local_rtf_estimate: float = Field(
        default=MEETINGS_LOCAL_RTF_ESTIMATE_DEFAULT,
        ge=0.05,
        le=20.0,
        description=(
            "Real-time factor of the LOCAL engine on this host (processing seconds "
            "per audio second), shown to the user as an ETA. Calibrate with "
            "`task meetings:probe:stt`; a Raspberry Pi is far slower than a dev box."
        ),
    )

    meetings_rate_limit_starts: int = Field(
        default=MEETINGS_RATE_LIMIT_STARTS_DEFAULT,
        ge=1,
        le=1000,
        description="Max recording starts per user per window (anti-runaway bound).",
    )

    meetings_rate_limit_window_seconds: int = Field(
        default=MEETINGS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=60,
        le=86400,
        description="Window of the start rate limit, in seconds.",
    )

    @property
    def meetings_segment_max_bytes(self) -> int:
        """Largest segment body the API accepts.

        Derived, never configured twice: raw 16 kHz int16 PCM is the densest
        format the client may send (32 000 bytes per second); Opus segments are
        an order of magnitude smaller and fit trivially. A 5 % margin absorbs
        container framing.
        """
        return int(STT_BYTES_PER_SECOND_AT_16KHZ_INT16 * self.meetings_segment_max_seconds * 1.05)

    @model_validator(mode="after")
    def _validate_bounds(self) -> MeetingsSettings:
        """Refuse configurations that would silently break the durability contract."""
        if self.meetings_job_heartbeat_interval_seconds >= self.meetings_job_lease_ttl_seconds:
            raise ValueError(
                "meetings_job_heartbeat_interval_seconds must be < "
                "meetings_job_lease_ttl_seconds "
                f"(got {self.meetings_job_heartbeat_interval_seconds} >= "
                f"{self.meetings_job_lease_ttl_seconds})"
            )
        if self.meetings_segment_max_seconds < self.meetings_segment_seconds:
            raise ValueError(
                "meetings_segment_max_seconds must be >= meetings_segment_seconds "
                f"(got {self.meetings_segment_max_seconds} < {self.meetings_segment_seconds})"
            )
        return self
