"""
Background chat runs configuration module.

Settings for the detached chat-run producer + Redis Streams broker
(ADR-117, Lot 1 durability). The feature is flag-gated and OFF by default:
when disabled, the SSE endpoint consumes the chat generator inline exactly
as before.

Created: 2026-07-09
Reference: docs/architecture/ADR-117-Background-Chat-Runs.md
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    DEFAULT_BACKGROUND_RUNS_ACTIVE_TTL_SECONDS,
    DEFAULT_BACKGROUND_RUNS_CANCEL_POLL_SECONDS,
    DEFAULT_BACKGROUND_RUNS_CANCEL_TTL_SECONDS,
    DEFAULT_BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS,
    DEFAULT_BACKGROUND_RUNS_HEARTBEAT_SECONDS,
    DEFAULT_BACKGROUND_RUNS_LISTENER_TTL_SECONDS,
    DEFAULT_BACKGROUND_RUNS_ORPHAN_GRACE_SECONDS,
    DEFAULT_BACKGROUND_RUNS_STREAM_MAXLEN,
    DEFAULT_BACKGROUND_RUNS_STREAM_SAFETY_TTL_SECONDS,
    DEFAULT_BACKGROUND_RUNS_STREAM_TTL_SECONDS,
    DEFAULT_BACKGROUND_RUNS_XREAD_BLOCK_MS,
    DEFAULT_SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS,
)


class BackgroundRunsSettings(BaseSettings):
    """Settings for detached (background) chat run execution."""

    background_runs_enabled: bool = Field(
        default=False,
        description=(
            "Master switch for detached chat-run execution. When true, the "
            "chat SSE endpoint spawns a detached producer publishing chunks "
            "to a Redis Stream and merely subscribes to it; the generation "
            "then survives client disconnects. When false, the legacy "
            "inline consumption path is used unchanged."
        ),
    )
    background_runs_stream_maxlen: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_STREAM_MAXLEN,
        ge=100,
        le=100_000,
        description=(
            "Approximate XADD MAXLEN cap per run stream. Bounds Redis memory "
            "if a run misbehaves. A normal run is well below this."
        ),
    )
    background_runs_stream_ttl_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_STREAM_TTL_SECONDS,
        ge=60,
        le=86_400,
        description=(
            "EXPIRE applied to the run stream when the terminal marker is "
            "published. Bounds memory; must exceed the longest window during "
            "which a reload may still want the history (Lot 2 reattach)."
        ),
    )
    background_runs_stream_safety_ttl_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_STREAM_SAFETY_TTL_SECONDS,
        ge=600,
        le=172_800,
        description=(
            "Safety EXPIRE armed at the FIRST chunk publication (EXPIRE NX "
            "piggybacked on every XADD — zero extra round-trip, never "
            "overwrites an existing TTL). Bounds the stream key lifetime when "
            "the producer dies without a terminal marker (hard kill, OOM, "
            "power loss). Must exceed the longest plausible run: a stream "
            "outliving it expires mid-run and loses its replay backlog (the "
            "next XADD re-creates the key and re-arms the TTL). publish_end "
            "still overwrites it with the short post-terminal TTL."
        ),
    )
    background_runs_xread_block_ms: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_XREAD_BLOCK_MS,
        ge=250,
        le=15_000,
        description=(
            "XREAD BLOCK window for subscribers. MUST stay well below "
            "REDIS_SOCKET_TIMEOUT*1000 (redis-py raises TimeoutError past "
            "it — proven by the 2026-07 de-risking POC). Also the natural "
            "keepalive cadence of the SSE subscriber."
        ),
    )
    background_runs_drain_timeout_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS,
        ge=5,
        le=300,
        description=(
            "Lifespan shutdown: max seconds to wait for in-flight chat "
            "producers before letting the worker exit (uvicorn worker "
            "recycling and docker stop both honor lifespan shutdown). "
            "Keep drain + generic-task timeouts below stop_grace_period."
        ),
    )
    shutdown_background_tasks_timeout_seconds: int = Field(
        default=DEFAULT_SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS,
        ge=1,
        le=120,
        description=(
            "Lifespan shutdown: max seconds to wait for generic "
            "fire-and-forget background tasks (memory/interest extraction, "
            "warmups) after chat producers are drained."
        ),
    )
    background_runs_active_ttl_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_ACTIVE_TTL_SECONDS,
        ge=5,
        le=120,
        description=(
            "TTL of the per-conversation active-run lock. Kept alive by the "
            "producer heartbeat; a killed producer therefore frees the "
            "conversation in at most this many seconds (POC-L2-1). Must be "
            "comfortably larger than the heartbeat period."
        ),
    )
    background_runs_heartbeat_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_HEARTBEAT_SECONDS,
        ge=1,
        le=60,
        description=(
            "Producer heartbeat period refreshing the active-run lock TTL. "
            "Keep it under active_ttl/2 so a single missed beat cannot "
            "expire a healthy run's lock."
        ),
    )
    background_runs_listener_ttl_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_LISTENER_TTL_SECONDS,
        ge=5,
        le=300,
        description=(
            "TTL of the per-stream subscriber-presence counter. Re-armed on "
            "INCR/DECR and periodically touched (~TTL/3) by attached "
            "subscribers; bounds staleness if a subscriber dies without "
            "decrementing. Voice synthesis is skipped when the counter is 0."
        ),
    )

    background_runs_cancel_poll_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_CANCEL_POLL_SECONDS,
        ge=1,
        le=10,
        description=(
            "Producer-side poll period for the user-cancellation signal "
            "(ADR-117 Lot 3). Bounds the stop-button latency: the run is "
            "cancelled within ~this many seconds of the request."
        ),
    )
    background_runs_cancel_ttl_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_CANCEL_TTL_SECONDS,
        ge=30,
        le=3600,
        description=(
            "TTL of the cancel-signal key. Self-cleans a signal whose "
            "producer already died (nothing left to cancel)."
        ),
    )
    background_runs_orphan_grace_seconds: int = Field(
        default=DEFAULT_BACKGROUND_RUNS_ORPHAN_GRACE_SECONDS,
        ge=5,
        le=300,
        description=(
            "Subscriber-side orphan grace period. The SSE relay exits with a "
            "synthetic error chunk once the conversation's active-run lock "
            "has been observed missing (or owned by another stream) for this "
            "long AND no chunk was received over the same window — the "
            "hard-kill escape hatch for subscribers on an orphaned stream. "
            "A heartbeated lock always wins over chunk silence (long LLM "
            "calls are silent but alive)."
        ),
    )

    @model_validator(mode="after")
    def _heartbeat_stays_under_half_the_lock_ttl(self) -> BackgroundRunsSettings:
        """Refuse to boot with a lock that would flap between heartbeats.

        A heartbeat period above TTL/2 means a single missed beat expires a
        HEALTHY run's lock — another run could then start concurrently on
        the same conversation (LangGraph thread race).
        """
        if self.background_runs_heartbeat_seconds > self.background_runs_active_ttl_seconds / 2:
            raise ValueError(
                "BACKGROUND_RUNS_HEARTBEAT_SECONDS must be <= "
                "BACKGROUND_RUNS_ACTIVE_TTL_SECONDS / 2 (got heartbeat="
                f"{self.background_runs_heartbeat_seconds}, "
                f"ttl={self.background_runs_active_ttl_seconds})"
            )
        return self

    @model_validator(mode="after")
    def _safety_ttl_covers_the_post_terminal_ttl(self) -> BackgroundRunsSettings:
        """Refuse a mid-run safety TTL shorter than the post-terminal TTL.

        The safety TTL protects a LIVE stream (armed at first publication);
        the short TTL covers a FINISHED one. A safety TTL below the short TTL
        would make a crashed run's stream vanish faster than a completed
        one — incoherent, and a symptom of swapped values.
        """
        if self.background_runs_stream_safety_ttl_seconds < self.background_runs_stream_ttl_seconds:
            raise ValueError(
                "BACKGROUND_RUNS_STREAM_SAFETY_TTL_SECONDS must be >= "
                "BACKGROUND_RUNS_STREAM_TTL_SECONDS (got safety="
                f"{self.background_runs_stream_safety_ttl_seconds}, "
                f"post_terminal={self.background_runs_stream_ttl_seconds})"
            )
        return self

    @model_validator(mode="after")
    def _orphan_grace_tolerates_one_missed_heartbeat(self) -> BackgroundRunsSettings:
        """Refuse an orphan grace that a single missed heartbeat could trip.

        The orphan exit is a last-resort escape hatch: it must only fire when
        the producer is genuinely gone. Below 2x the heartbeat period, one
        late beat plus probe jitter could push a HEALTHY silent run over the
        threshold and surface a false error to the subscriber.
        """
        if self.background_runs_orphan_grace_seconds < 2 * self.background_runs_heartbeat_seconds:
            raise ValueError(
                "BACKGROUND_RUNS_ORPHAN_GRACE_SECONDS must be >= "
                "2 * BACKGROUND_RUNS_HEARTBEAT_SECONDS (got grace="
                f"{self.background_runs_orphan_grace_seconds}, "
                f"heartbeat={self.background_runs_heartbeat_seconds})"
            )
        return self
