"""
Detached chat-run producer (ADR-117, Lot 1).

Consumes an AgentService chat-chunk generator INDEPENDENTLY of any HTTP
connection and publishes every chunk to the run's Redis Stream. The SSE
endpoint (and, in Lot 2, reattaching clients) merely subscribe.

Invariants:
  - The stream ALWAYS ends with a terminal marker, whatever the exit path
    (completed / error / killed) — subscribers can never hang forever.
  - The generator's own finalization (archiving, token tracking, HITL
    cleanup) runs inside the generator itself; this module only adds the
    transport-level guarantees plus a best-effort partial-content
    finalizer for the hard-kill path.
  - Producers register in a module-level set drained by the lifespan
    shutdown (see main.py) — proven necessary by the 2026-07 de-risking
    POC: without the drain, uvicorn worker recycling kills in-flight runs.
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress

from redis.asyncio import Redis

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    chat_background_producers_active,
    chat_background_runs_total,
    e2e_request_duration_with_agents,
)
from src.infrastructure.streaming.run_stream_broker import (
    clear_cancel,
    is_cancel_requested,
    publish_chunk,
    publish_end,
    refresh_active_run,
    release_active_run,
)

logger = get_logger(__name__)

PartialFinalizer = Callable[[str, str], Awaitable[None]]

_producers: set[asyncio.Task] = set()


def get_active_chat_producer_count() -> int:
    """Number of detached chat producers currently running in this worker."""
    return len(_producers)


def spawn_chat_run_producer(
    *,
    chat_stream: AsyncGenerator[ChatStreamChunk, None],
    run_id: str,
    stream_id: str,
    user_id: str,
    session_id: str,
    finalize_partial: PartialFinalizer | None = None,
    conversation_id: str | None = None,
) -> asyncio.Task:
    """Start the detached producer task for one chat run.

    Args:
        chat_stream: The AgentService chunk generator (not yet consumed).
        run_id: BILLING/correlation identifier (reused across HITL
            interrupt + resumption for token aggregation).
        stream_id: TRANSPORT identifier — the Redis stream key suffix.
            MUST be fresh per invocation: a HITL resumption reuses run_id,
            and publishing to the same stream would append after the
            interrupt phase's terminal marker, so a replay-from-0
            subscriber would stop at the stale marker and never see the
            resumption content.
        user_id: User id (logging only; no PII beyond the id).
        session_id: Session id (logging only).
        finalize_partial: Optional async callback invoked with
            (accumulated_content, reason) when the producer is killed
            before the generator could finish (best-effort, shielded).
        conversation_id: When provided (Lot 2), the caller has ALREADY
            acquired the conversation's active-run lock; the producer
            keeps it alive (heartbeat) and releases it on every exit
            path. None = no lock bookkeeping (tests, legacy callers).

    Returns:
        The producer task (registered for lifespan drain).
    """
    task = asyncio.create_task(
        _produce(
            chat_stream, run_id, stream_id, user_id, session_id, finalize_partial, conversation_id
        ),
        name=f"chat-run-producer-{stream_id}",
    )
    _producers.add(task)
    chat_background_producers_active.set(len(_producers))

    def _on_done(t: asyncio.Task) -> None:
        _producers.discard(t)
        chat_background_producers_active.set(len(_producers))

    task.add_done_callback(_on_done)
    logger.info(
        "chat_run_producer_started",
        run_id=run_id,
        stream_id=stream_id,
        user_id=user_id,
        session_id=session_id,
        active_producers=len(_producers),
    )
    return task


async def _produce(
    chat_stream: AsyncGenerator[ChatStreamChunk, None],
    run_id: str,
    stream_id: str,
    user_id: str,
    session_id: str,
    finalize_partial: PartialFinalizer | None,
    conversation_id: str | None = None,
) -> None:
    """Consume the generator and publish chunks; always publish an end marker."""
    redis = await get_redis_cache()
    start_time = time.time()
    intention_label = "unknown"
    response_content = ""
    chunk_count = 0
    # Lot 2: keep the caller-acquired active-run lock alive for the whole run
    heartbeat_task: asyncio.Task | None = None
    if conversation_id is not None:
        heartbeat_task = asyncio.create_task(
            _heartbeat_active_run(redis, conversation_id, stream_id),
            name=f"chat-run-heartbeat-{stream_id}",
        )
    # Lot 3: watch for a user cancellation signal (possibly set from another
    # worker) and cancel THIS task cooperatively. The flag distinguishes a
    # user cancel from a hard kill (shutdown drain) in the terminal status.
    cancel_state = {"requested": False}
    producer_task = asyncio.current_task()
    cancel_watch_task: asyncio.Task | None = None
    if producer_task is not None:
        cancel_watch_task = asyncio.create_task(
            _watch_cancel(redis, stream_id, cancel_state, producer_task),
            name=f"chat-run-cancel-watch-{stream_id}",
        )
    try:
        async for chunk in chat_stream:
            if chunk.type == "router_decision" and chunk.metadata:
                intention_label = chunk.metadata.get("intention", "unknown")
            # Mirror the archive accumulation rule of the service layer:
            # tokens append, content_replacement REPLACES (photo injection).
            if chunk.type == "token" and isinstance(chunk.content, str):
                response_content += chunk.content
            elif chunk.type == "content_replacement" and isinstance(chunk.content, str):
                response_content = chunk.content
            await publish_chunk(redis, stream_id, chunk.model_dump_json())
            chunk_count += 1
    except asyncio.CancelledError:
        # User cancellation (Lot 3, cooperative via the cancel watcher) or
        # hard kill (drain timeout / loop teardown). Either way the
        # generator's async-with blocks have run their __aexit__ (tracking
        # persisted). Best-effort: mark the stream, archive the partial.
        status = "cancelled" if cancel_state["requested"] else "killed"
        with suppress(Exception):
            await asyncio.shield(
                _finalize_abnormal(redis, stream_id, status, response_content, finalize_partial)
            )
        raise
    except Exception as exc:  # noqa: BLE001 — top-level task boundary
        # The generator already emitted its own error + done chunks before
        # raising (service.py contract) — they were published above.
        logger.error(
            "chat_run_producer_error",
            run_id=run_id,
            stream_id=stream_id,
            error=str(exc),
            error_type=type(exc).__name__,
            chunks_published=chunk_count,
        )
        # Best-effort: if Redis itself is the failure cause, publish_end
        # cannot succeed either — subscribers will then error out on their
        # own XREAD, so nothing is left hanging.
        with suppress(Exception):
            await publish_end(redis, stream_id, "error")
        chat_background_runs_total.labels(status="error").inc()
        return
    finally:
        # Lock/watcher bookkeeping runs on EVERY exit path: stop the
        # heartbeat and the cancel watcher, release the lock (zombie-safe by
        # value), and consume any pending cancel signal — all shielded so a
        # propagating cancellation cannot abort them.
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        if cancel_watch_task is not None and not cancel_watch_task.done():
            cancel_watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await cancel_watch_task
        if cancel_state["requested"]:
            with suppress(Exception):
                await asyncio.shield(clear_cancel(redis, stream_id))
        if conversation_id is not None:
            with suppress(Exception):
                await asyncio.shield(release_active_run(redis, conversation_id, stream_id))
    # Normal completion
    await publish_end(redis, stream_id, "completed")
    chat_background_runs_total.labels(status="completed").inc()
    e2e_request_duration_with_agents.labels(
        intention=intention_label, agents_bucket="single"
    ).observe(time.time() - start_time)
    logger.info(
        "chat_run_producer_completed",
        run_id=run_id,
        stream_id=stream_id,
        user_id=user_id,
        session_id=session_id,
        chunks_published=chunk_count,
        duration_seconds=round(time.time() - start_time, 2),
        intention=intention_label,
    )


async def _watch_cancel(
    redis: Redis,
    stream_id: str,
    cancel_state: dict[str, bool],
    producer_task: asyncio.Task,
) -> None:
    """Poll the cancel signal and cooperatively cancel the producer (Lot 3).

    The signal may be set from ANY worker (the stop button's POST can land
    anywhere); the watcher runs next to the producer, so the asyncio
    cancellation itself stays worker-local. Marks ``cancel_state`` BEFORE
    cancelling so the terminal status reads "cancelled", not "killed".
    """
    period = settings.background_runs_cancel_poll_seconds
    while True:
        await asyncio.sleep(period)
        try:
            requested = await is_cancel_requested(redis, stream_id)
        except Exception as exc:  # noqa: BLE001 — transient Redis hiccup: keep polling
            logger.warning("cancel_watch_poll_failed", stream_id=stream_id, error=str(exc))
            continue
        if requested:
            cancel_state["requested"] = True
            logger.info("chat_run_cancelling", stream_id=stream_id)
            producer_task.cancel()
            return


async def _heartbeat_active_run(redis: Redis, conversation_id: str, stream_id: str) -> None:
    """Periodically re-arm the active-run lock TTL while the run is alive.

    Stops by itself when the lock is lost (expired or taken over by a newer
    run) — a zombie producer must never keep a conversation locked.
    """
    period = settings.background_runs_heartbeat_seconds
    while True:
        await asyncio.sleep(period)
        try:
            still_owner = await refresh_active_run(redis, conversation_id, stream_id)
        except Exception as exc:  # noqa: BLE001 — transient Redis hiccup: keep trying
            logger.warning(
                "active_run_heartbeat_failed",
                conversation_id=conversation_id,
                stream_id=stream_id,
                error=str(exc),
            )
            continue
        if not still_owner:
            logger.warning(
                "active_run_lock_lost",
                conversation_id=conversation_id,
                stream_id=stream_id,
            )
            return


async def _finalize_abnormal(
    redis: Redis,
    stream_id: str,
    status: str,
    response_content: str,
    finalize_partial: PartialFinalizer | None,
) -> None:
    """Terminal marker + optional partial-content archive on abnormal end."""
    if status == "cancelled":
        # User cancellation (Lot 3): the generator died before emitting its
        # own done chunk — synthesize one so subscribers finish their normal
        # SSE lifecycle and can badge the partial bubble. Standard chunk
        # type, no contract change; token totals are archived in DB (the
        # tracker committed on exit) and reconcile on the next reload.
        done_chunk = ChatStreamChunk(
            type="done",
            content="",
            metadata={"cancelled": True},
        )
        await publish_chunk(redis, stream_id, done_chunk.model_dump_json())
    await publish_end(redis, stream_id, status)
    chat_background_runs_total.labels(status=status).inc()
    if finalize_partial is not None and response_content.strip():
        await finalize_partial(response_content, status)
    logger.warning(
        "chat_run_producer_aborted",
        stream_id=stream_id,
        status=status,
        partial_content_length=len(response_content),
    )


async def drain_chat_producers(timeout: float) -> tuple[int, int]:
    """Wait for in-flight producers at shutdown (POC-4b mitigation).

    Args:
        timeout: Max seconds to wait.

    Returns:
        (completed, still_pending) task counts.
    """
    if not _producers:
        return (0, 0)
    logger.info("chat_producers_drain_started", count=len(_producers), timeout=timeout)
    done, pending = await asyncio.wait(set(_producers), timeout=timeout)
    logger.info("chat_producers_drain_finished", done=len(done), pending=len(pending))
    return (len(done), len(pending))
