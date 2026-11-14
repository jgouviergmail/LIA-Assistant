"""One supervised chat producer for inline SSE and reconnectable Redis streams.

The producer owns the generator, its finalization and durable admission. A
subscriber owns only its transport. Inline disconnection cancels the producer;
a detached run continues archiving to the immutable target it admitted.
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from functools import partial

import structlog
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import STREAM_TEARDOWN_WAIT_SECONDS
from src.core.conversation_execution import ExecutionRevoked, RunAdmission, RunEnd
from src.core.i18n import resolve_language
from src.core.run_authority import current_run_authority, run_authority_scope
from src.domains.agents.api.error_messages import SSEErrorMessages
from src.domains.agents.api.run_output import (
    InlineRunOutput,
    RedisRunOutput,
    RunEndStatus,
    RunOutput,
)
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.stream_identity import with_invocation_identity
from src.domains.agents.utils.hitl_store import HITLStore
from src.infrastructure.async_utils import cancel_and_join, finish_owned_task, safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_agents import (
    chat_background_producers_active,
    chat_background_runs_total,
    e2e_request_duration_with_agents,
)
from src.infrastructure.streaming.run_admission import owned_execution, release_unstarted_execution
from src.infrastructure.streaming.run_stream_broker import clear_cancel, is_cancel_requested

logger = structlog.get_logger(__name__)
PartialFinalizer = Callable[[str, str], Awaitable[None]]
_producers: dict[asyncio.Task[None], bool] = {}


@dataclass(slots=True)
class _Progress:
    """One invocation's observed output; no user content appears in operational logs."""

    pieces: list[str] = field(default_factory=list)
    chunks: int = 0
    intention: str = "unknown"
    done: bool = False
    error: bool = False
    cancel_requested: bool = False

    def observe(self, chunk: ChatStreamChunk) -> None:
        """Match the archive's replacement semantics without quadratic concatenation."""
        self.chunks += 1
        if chunk.type == "token" and isinstance(chunk.content, str):
            self.pieces.append(chunk.content)
        elif chunk.type == "content_replacement" and isinstance(chunk.content, str):
            self.pieces = [chunk.content]
        if chunk.type == "router_decision" and chunk.metadata:
            intention = chunk.metadata.get("intention")
            if isinstance(intention, str):
                self.intention = intention


def get_active_chat_producer_count() -> int:
    """Count actual producer tasks, including inline runs that are being drained."""
    return len(_producers)


def spawn_chat_run_producer(
    *,
    chat_stream: AsyncGenerator[ChatStreamChunk],
    admission: RunAdmission,
    session_id: str,
    finalize_partial: PartialFinalizer | None = None,
    output: RunOutput | None = None,
) -> asyncio.Task[None]:
    """Transfer a committed admission to an immediately owned producer task.

    Args:
        chat_stream: Unconsumed engine stream; its contexts close in this task.
        admission: Private SQL authority already committed by the request.
        session_id: Correlation identifier, never the bearer session cookie.
        finalize_partial: Pinned archive callback for interrupted output.
        output: Inline queue owned by the request, or the default Redis relay.

    Returns:
        The registered task. Cancelling it before it starts still releases its
        unused admission through an owned callback, never a timer.
    """
    sink = output or (
        RedisRunOutput(admission.stream_id) if admission.relayed else InlineRunOutput()
    )
    started = False

    async def produce_owned() -> None:
        nonlocal started
        started = True
        entered = False
        startup_status: RunEndStatus = "killed"
        try:
            async with owned_execution(admission):
                entered = True
                await _produce(chat_stream, admission, session_id, sink, finalize_partial)
        except Exception as failure:
            if not entered:
                startup_status = "error"
                await finish_owned_task(
                    asyncio.create_task(_report_startup_failure(sink, admission, failure))
                )
            raise
        finally:
            if not entered:
                await finish_owned_task(
                    asyncio.create_task(_unstarted_output(chat_stream, sink, startup_status))
                )

    # A new producer owns, never borrows, even if a composition caller happened
    # to have another graph context. Keep all other accounting/language scopes.
    with run_authority_scope(None):
        task = asyncio.create_task(produce_owned(), name=f"chat-run-producer-{admission.stream_id}")
    _producers[task] = admission.relayed
    _update_active_gauge()

    def finished(done: asyncio.Task[None]) -> None:
        _producers.pop(done, None)
        _update_active_gauge()
        if not started:
            safe_fire_and_forget(
                _release_unstarted(chat_stream, admission, sink),
                name="chat_run_unstarted_cleanup",
                independent_of_graph=True,
            )
        if not done.cancelled() and (failure := done.exception()) is not None:
            logger.error(
                "chat_run_owner_failed",
                activity_id=str(admission.activity_id),
                error_type=type(failure).__name__,
            )

    task.add_done_callback(finished)
    return task


def _update_active_gauge() -> None:
    """The existing background metric counts only reconnectable runs."""
    chat_background_producers_active.set(sum(_producers.values()))


async def _unstarted_output(
    stream: AsyncGenerator[ChatStreamChunk],
    output: RunOutput,
    status: RunEndStatus = "killed",
) -> None:
    """A refused startup cannot leave a reader waiting for a first chunk forever."""
    await stream.aclose()
    await _best_effort(lambda: output.finish(status), "chat_run_unstarted_end_failed")


async def _report_startup_failure(
    output: RunOutput,
    admission: RunAdmission,
    failure: Exception,
) -> None:
    """Refused authority is an explicit failed request, never an empty successful answer."""
    for chunk in (
        ChatStreamChunk(
            type="error",
            content=SSEErrorMessages.stream_error(failure, language=resolve_language()),
            metadata={"error_type": "stream_error"},
        ),
        ChatStreamChunk(type="done", content="", metadata={"error": True}),
    ):
        scoped = with_invocation_identity(chunk, admission)
        await _best_effort(partial(output.publish, scoped), "chat_run_startup_error_publish_failed")


async def _release_unstarted(
    stream: AsyncGenerator[ChatStreamChunk],
    admission: RunAdmission,
    output: RunOutput,
) -> None:
    """The task's first instruction never ran: there can be no graph or Redis writer."""

    async def close() -> None:
        await release_unstarted_execution(admission)
        await _unstarted_output(stream, output)

    await finish_owned_task(asyncio.create_task(close()))


def link_inline_request_lifetime(producer: asyncio.Task[None], output: InlineRunOutput) -> None:
    """A request ending before response iteration still abandons its inline producer."""
    request = asyncio.current_task()
    assert request is not None

    def abandon(_request: asyncio.Task[object]) -> None:
        output.abandon()
        if not producer.done() and not producer.cancelling():
            producer.cancel()

    request.add_done_callback(abandon)


async def stop_inline_producer(producer: asyncio.Task[None], output: InlineRunOutput) -> None:
    """Release transport backpressure before asking the owner to stop and drain."""
    output.abandon()
    if not producer.done() and not producer.cancelling():
        producer.cancel()
    # Its owner and SQL admission stay indexed if physical teardown takes longer.
    await asyncio.wait({producer}, timeout=STREAM_TEARDOWN_WAIT_SECONDS)


async def _produce(
    chat_stream: AsyncGenerator[ChatStreamChunk],
    admission: RunAdmission,
    session_id: str,
    output: RunOutput,
    finalize_partial: PartialFinalizer | None,
) -> None:
    """Drive both transports through the same generator and owned finalization."""
    redis = await get_redis_cache()
    producer = asyncio.current_task()
    assert producer is not None
    progress = _Progress()
    status: RunEndStatus = "completed"
    failure: Exception | None = None
    started_at = time.monotonic()
    watcher = asyncio.create_task(_watch_cancel(redis, admission.stream_id, progress, producer))
    try:
        async with aclosing(chat_stream):
            async for chunk in chat_stream:
                progress.observe(chunk)
                await output.publish(with_invocation_identity(chunk, admission))
                progress.done |= chunk.type == "done"
                progress.error |= chunk.type == "error"
    except asyncio.CancelledError:
        authority = current_run_authority()
        if authority is not None and authority.supervision_lost and not progress.cancel_requested:
            status = "error"
            failure = ExecutionRevoked()
        else:
            status = "cancelled" if progress.cancel_requested else "killed"
        raise
    except Exception as exc:
        status, failure = "error", exc
        logger.error(
            "chat_run_producer_error",
            activity_id=str(admission.activity_id),
            error_type=type(exc).__name__,
            chunks_observed=progress.chunks,
        )
    finally:
        authority = current_run_authority()
        if authority is not None:
            # Its close settles what waited by this declaration (ADR-384): an
            # answer that published an error did not end normally.
            normal = status == "completed" and not progress.error
            authority.end = RunEnd.NORMAL if normal else RunEnd.INTERRUPTED
            authority.revoked = True
        # Revocation stops graph children now. The owner still holds its SQL
        # activity while the explicitly pinned finalizer files prior output.
        await finish_owned_task(
            asyncio.create_task(
                _close_producer(
                    redis,
                    admission,
                    output,
                    watcher,
                    progress,
                    status,
                    failure,
                    finalize_partial,
                )
            )
        )
        duration = time.monotonic() - started_at
        e2e_request_duration_with_agents.labels(
            intention=progress.intention,
            agents_bucket="single",
        ).observe(duration)
        if admission.relayed:
            chat_background_runs_total.labels(status=status).inc()
        logger.info(
            "chat_run_producer_finished",
            activity_id=str(admission.activity_id),
            session_id=session_id,
            status=status,
            chunks_observed=progress.chunks,
            duration_seconds=round(duration, 2),
        )


async def _watch_cancel(
    redis: Redis,
    stream_id: str,
    progress: _Progress,
    producer: asyncio.Task[object],
) -> None:
    """The signal may come from any worker; cancellation stays with this actual owner."""
    while True:
        await asyncio.sleep(settings.background_runs_cancel_poll_seconds)
        try:
            requested = await is_cancel_requested(redis, stream_id)
        except Exception as exc:
            logger.warning(
                "cancel_watch_poll_failed", stream_id=stream_id, error_type=type(exc).__name__
            )
            continue
        if requested:
            progress.cancel_requested = True
            if not producer.cancelling():
                producer.cancel()
            return


async def _close_producer(
    redis: Redis,
    admission: RunAdmission,
    output: RunOutput,
    watcher: asyncio.Task[None],
    progress: _Progress,
    status: RunEndStatus,
    failure: Exception | None,
    finalize_partial: PartialFinalizer | None,
) -> None:
    """Archive independently of transport availability; a second stop cannot detach it."""
    await cancel_and_join(watcher)
    if status != "completed":
        content = "".join(progress.pieces)
        if finalize_partial is not None and content.strip():
            await _best_effort(
                lambda: finalize_partial(content, status), "chat_run_partial_archive_failed"
            )
    if status == "cancelled":
        store = HITLStore(redis, settings.hitl_pending_data_ttl_seconds)
        await _best_effort(
            lambda: store.clear_interrupt_for_run(
                str(admission.target.runtime_id),
                admission.run_id,
                activity_id=admission.activity_id,
            ),
            "chat_run_question_cleanup_failed",
        )
        await _best_effort(
            lambda: clear_cancel(redis, admission.stream_id), "chat_run_cancel_cleanup_failed"
        )
    for chunk in _terminal_chunks(progress, status, failure):
        await _best_effort(
            partial(output.publish, with_invocation_identity(chunk, admission)),
            "chat_run_terminal_publish_failed",
        )
    await _best_effort(lambda: output.finish(status), "chat_run_end_publish_failed")


def _terminal_chunks(
    progress: _Progress,
    status: RunEndStatus,
    failure: Exception | None,
) -> list[ChatStreamChunk]:
    """Missing terminal events are derived from acknowledged delivery, never attempted output."""
    chunks: list[ChatStreamChunk] = []
    if failure is not None and not progress.error:
        chunks.append(
            ChatStreamChunk(
                type="error",
                content=SSEErrorMessages.stream_error(failure, language=resolve_language()),
                metadata={"error_type": "stream_error"},
            )
        )
    if status in ("cancelled", "error") and not progress.done:
        chunks.append(ChatStreamChunk(type="done", content="", metadata={status: True}))
    return chunks


async def _best_effort[T](action: Callable[[], Awaitable[T]], event: str) -> None:
    """A transport failure never suppresses independent archive or cleanup attempts."""
    try:
        await action()
    except Exception as exc:
        logger.warning(event, error_type=type(exc).__name__)


async def drain_chat_producers(timeout: float) -> tuple[int, int]:
    """Wait for actual producers at shutdown; unknown stops retain their SQL admission."""
    if not _producers:
        return 0, 0
    done, pending = await asyncio.wait(set(_producers), timeout=timeout)
    logger.info("chat_producers_drain_finished", done=len(done), pending=len(pending))
    return len(done), len(pending)
