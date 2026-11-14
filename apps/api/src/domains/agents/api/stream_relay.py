"""A reconnectable subscriber follows SQL liveness; it never closes execution authority."""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import structlog
from redis.asyncio import Redis

from src.core.config import settings
from src.core.conversation_execution import ExecutionPhase
from src.core.conversation_target import ConversationRef
from src.core.i18n_types import Language
from src.domains.agents.api.error_messages import SSEErrorMessages
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.session_watch import SESSION_REVOKED_COMMENT, session_still_valid
from src.domains.agents.api.stream_identity import stream_metadata
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics_agents import sse_streaming_errors_total
from src.infrastructure.streaming.run_stream_broker import (
    listener_decr,
    listener_incr,
    listener_touch,
    subscribe,
)

logger = structlog.get_logger(__name__)
type TransportState = Literal["running", "closed", "unknown"]
type SilenceVerdict = Literal["continue", "end", "interrupted"]


@dataclass(slots=True)
class _Silence:
    """Only prolonged, unconfirmed silence ends observation; fresh supervision resets it."""

    last_chunk: float = field(default_factory=time.monotonic)
    unknown_since: float | None = None
    delivered_done: bool = False

    def observed(self, chunk_type: str | None) -> None:
        self.last_chunk, self.unknown_since = time.monotonic(), None
        self.delivered_done |= chunk_type == "done"

    async def verdict(self, target: ConversationRef | None, stream_id: str) -> SilenceVerdict:
        grace = settings.background_runs_orphan_grace_seconds
        if target is None or time.monotonic() - self.last_chunk < grace:
            return "continue"
        state = await transport_state(target, stream_id)
        if state == "closed" and self.delivered_done:
            return "end"
        if state == "running":
            self.unknown_since = None
            return "continue"
        if self.unknown_since is None:
            self.unknown_since = time.monotonic()
        if time.monotonic() - self.unknown_since >= grace:
            return "interrupted"
        return "continue"


async def transport_state(target: ConversationRef, stream_id: str) -> TransportState:
    """A stale heartbeat ends only observation, never an occupied SQL admission."""
    try:
        async with get_db_context() as db:
            snapshot = await ConversationExecutionRepository(db).snapshot_for_owner(
                target.owner_id,
                stream_id=stream_id,
            )
    except Exception as exc:
        logger.warning(
            "run_stream_probe_unavailable", stream_id=stream_id, error_type=type(exc).__name__
        )
        return "unknown"
    if snapshot is None or snapshot.busy.target != target:
        return "unknown"
    if snapshot.busy.phase == ExecutionPhase.CLOSED:
        return "closed"
    age = (datetime.now(UTC) - snapshot.heartbeat_at).total_seconds()
    if (
        snapshot.busy.phase == ExecutionPhase.RUNNING
        and age < settings.background_runs_active_ttl_seconds
    ):
        return "running"
    return "unknown"


def _chunk_type(payload: str) -> str | None:
    """Decode only candidate control/audio chunks, never search their prose as a verdict."""
    if '"voice_audio_chunk"' not in payload and '"done"' not in payload:
        return None
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("type"), str):
        return str(data["type"])
    return None


def _interrupted_frames(
    target: ConversationRef,
    run_id: str,
    stream_id: str,
    language: Language | None,
) -> tuple[str, str]:
    """An unknown transport is stated as such; no restart or safe retry is invented."""
    scope = stream_metadata(target, run_id, stream_id)
    error = ChatStreamChunk(
        type="error",
        content=SSEErrorMessages.run_orphaned(language),
        metadata={"error_type": "orphaned_run", **scope},
    )
    done = ChatStreamChunk(
        type="done",
        content="",
        metadata={"error": True, "orphaned": True, **TokenSummaryDTO.zero().to_metadata(), **scope},
    )
    return f"data: {error.model_dump_json()}\n\n", f"data: {done.model_dump_json()}\n\n"


async def _heartbeat_frames(
    silence: _Silence,
    target: ConversationRef | None,
    run_id: str | None,
    stream_id: str,
    language: Language | None,
    session_id: str | None,
) -> tuple[tuple[str, ...], bool]:
    """Recheck the subscriber and the silent execution without confusing either lifetime."""
    if not await session_still_valid(session_id):
        return (SESSION_REVOKED_COMMENT,), True
    verdict = await silence.verdict(target, stream_id)
    if verdict == "end":
        return (), True
    if verdict == "interrupted":
        assert target is not None and run_id is not None
        sse_streaming_errors_total.labels(
            error_type="orphaned_run", node_name="run_stream_relay"
        ).inc()
        return _interrupted_frames(target, run_id, stream_id, language), True
    return (": heartbeat\n\n",), False


async def _renew_presence(redis: Redis, stream_id: str, last_touch: float) -> float:
    """Presence remains advisory; its bounded TTL expires if renewal fails."""
    if time.monotonic() - last_touch <= settings.background_runs_listener_ttl_seconds / 3:
        return last_touch
    # A failed presence update never establishes that the executing producer stopped.
    with suppress(Exception):
        await listener_touch(redis, stream_id)
    return time.monotonic()


async def stream_run_as_sse(
    stream_id: str,
    *,
    target: ConversationRef | None = None,
    run_id: str | None = None,
    user_language: Language | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str]:
    """Replay then relay; HTTP callers always provide their authorized frozen scope.

    The optional scope supports direct transport tests. It grants no permission:
    every HTTP subscription is admitted by the owning router beforehand. Fresh
    SQL supervision keeps a silent model call alive even without any Redis lease.
    """
    if target is not None and run_id is None:
        raise ValueError("A scoped stream requires its billing correlation")
    redis = await get_redis_cache()
    await listener_incr(redis, stream_id)
    last_touch = time.monotonic()
    silence = _Silence()
    replay_boundary = False
    try:
        yield "retry: 5000\n\n"
        async for event in subscribe(redis, stream_id):
            last_touch = await _renew_presence(redis, stream_id, last_touch)
            if not event.is_replay and not replay_boundary:
                yield ": replay-end\n\n"
                replay_boundary = True
            if event.kind == "end":
                return
            if event.kind == "chunk":
                kind = _chunk_type(event.payload)
                silence.observed(kind)
                if event.is_replay and kind == "voice_audio_chunk":
                    continue
                yield f"data: {event.payload}\n\n"
                if not event.is_replay:
                    await asyncio.sleep(settings.agent_stream_sleep_interval)
                continue
            frames, ended = await _heartbeat_frames(
                silence, target, run_id, stream_id, user_language, session_id
            )
            for frame in frames:
                yield frame
            if ended:
                return
    finally:
        # The subscriber releases presence only. SQL occupancy belongs to its producer.
        with suppress(Exception):
            await listener_decr(redis, stream_id)
