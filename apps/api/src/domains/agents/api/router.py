"""
Agents domain router.
FastAPI endpoints for chat with SSE streaming.
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
from datetime import UTC
from typing import TYPE_CHECKING

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    HITL_RATE_LIMIT_REQUESTS,
    HITL_RATE_LIMIT_WINDOW_SECONDS,
)
from src.core.exceptions import raise_not_found_or_unauthorized, raise_user_id_mismatch
from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_CONTENT,
    FIELD_ERROR_TYPE,
    FIELD_METADATA,
    FIELD_RUN_ID,
    FIELD_STATUS,
)
from src.core.i18n import DEFAULT_LANGUAGE, Language
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_hitl import get_user_language
from src.core.session_dependencies import get_current_active_session
from src.core.user_display import resolve_user_display_name
from src.domains.agents.api.background_runner import (
    PartialFinalizer,
    spawn_chat_run_producer,
)
from src.domains.agents.api.error_messages import SSEErrorMessages
from src.domains.agents.api.hitl_pending import check_pending_hitl, check_pending_hitl_uncached
from src.domains.agents.api.schemas import ChatRequest, ChatStreamChunk, PendingHitlResponse
from src.domains.agents.api.service import AgentService
from src.domains.agents.api.session_watch import (
    SESSION_REVOKED_COMMENT,
    session_still_valid,
)
from src.domains.agents.api.sse_keepalive import KeepalivePulse, iter_with_keepalive
from src.domains.agents.utils import generate_run_id
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    e2e_request_duration_with_agents,
    sse_streaming_errors_total,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# Global service instance (singleton) - Thread-safe lazy initialization
_agent_service: AgentService | None = None
_agent_service_lock = threading.Lock()

# PHASE 8.1.3: the in-memory pending-HITL detection cache lives in
# src.domains.agents.utils.hitl_cache — HITLStore.save/delete invalidate it
# at the source, so router-level invalidation hooks are no longer needed.


def get_agent_service() -> AgentService:
    """
    Get or create agent service singleton (thread-safe lazy initialization).

    Uses double-checked locking pattern to avoid race conditions during initialization
    while minimizing lock contention for subsequent calls.
    """
    global _agent_service

    # First check (unlocked) - fast path for already initialized
    if _agent_service is not None:
        return _agent_service

    # Second check (locked) - ensure only one thread initializes
    with _agent_service_lock:
        if _agent_service is None:
            _agent_service = AgentService()

    return _agent_service


async def _probe_orphan(
    redis: "Redis",
    conversation_id: str,
    stream_id: str,
    lock_missing_since: float | None,
    grace_seconds: float,
) -> tuple[float | None, bool]:
    """One orphan-detection probe (run on keepalives during chunk silence).

    The conversation's heartbeated active-run lock is the source of truth
    for producer liveness — NOT chunk silence (a long LLM call is silent but
    alive). The run is declared orphaned only once the lock has been
    observed missing (or owned by another stream) for a full grace period.

    A probe failure is NOT evidence of a missing lock: the marker is left
    untouched and the verdict stays False — same philosophy as the
    producer's heartbeat and cancel watchers, which skip transient Redis
    hiccups instead of acting on them.

    Args:
        redis: Redis client.
        conversation_id: Conversation whose active-run lock to probe.
        stream_id: The stream this subscriber follows (expected lock owner).
        lock_missing_since: Monotonic timestamp of the first consecutive
            missing/foreign observation, or None if the lock was owned by
            this stream at the last probe.
        grace_seconds: How long the lock must stay missing before the
            orphan verdict.

    Returns:
        (updated ``lock_missing_since``, orphan verdict).
    """
    from src.infrastructure.streaming.run_stream_broker import get_active_run

    try:
        active = await get_active_run(redis, conversation_id)
    except Exception as exc:  # noqa: BLE001 — transient Redis hiccup: skip this probe
        logger.debug("run_stream_orphan_probe_failed", stream_id=stream_id, error=str(exc))
        return lock_missing_since, False
    if active is not None and active.get("stream_id") == stream_id:
        return None, False  # lock alive and ours: the producer is heartbeating
    now = time.monotonic()
    if lock_missing_since is None:
        return now, False
    return lock_missing_since, (now - lock_missing_since) >= grace_seconds


async def stream_run_as_sse(
    stream_id: str,
    conversation_id: str | None = None,
    user_language: Language = DEFAULT_LANGUAGE,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Subscribe to a run stream and format events as SSE lines.

    Transport-only (ADR-117): chunks are relayed verbatim (already-serialized
    ChatStreamChunk JSON), empty XREAD windows become heartbeats, the broker
    end marker terminates the generator. Client disconnects cancel THIS
    generator only — the detached producer is unaffected (proven by the
    2026-07 de-risking POC).

    Lot 2 semantics:
      - Subscriber presence is tracked (INCR/DECR around the whole read) —
        voice synthesis is skipped by the producer when nobody listens.
      - Replay entries (backlog existing before this subscriber attached)
        are relayed WITHOUT pacing, with ``voice_audio_chunk`` payloads
        dropped (stale audio), and the transport comment ``: replay-end``
        is emitted at the replay→live boundary so reattaching clients can
        lift their replay-mode side-effect suppression. Legacy clients
        ignore unknown SSE comments — the chunk contract is untouched.

    Hard-kill hardening (2026-07 audit): a producer dying without its
    terminal marker (kill -9, OOM, power loss — the end-marker invariant
    only covers in-process exits) would leave this relay looping on
    keepalives forever. Once the conversation's active-run lock has been
    observed missing (or owned by another stream) for a full grace period
    AND no chunk arrived over the same window, the relay emits a synthetic
    ``error`` + ``done`` chunk pair (standard types — the exact sequence of
    the endpoint's exception fallback) and terminates. With
    ``conversation_id=None`` (no lock was ever acquired: e.g. first message
    of a brand-new user) the detection is disabled — lock absence would be
    the normal state, not a death certificate.

    Args:
        stream_id: Transport identifier (stream key suffix) — fresh per
            invocation, distinct from the billing run_id on HITL resumption.
        conversation_id: Scope of the active-run lock used for orphan
            detection; None disables the detection.
        user_language: Language of the synthetic orphan error message.

    Yields:
        SSE-formatted lines (``data: ...`` frames and transport comments).
    """
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.streaming.run_stream_broker import (
        listener_decr,
        listener_incr,
        listener_touch,
        subscribe,
    )

    redis = await get_redis_cache()
    await listener_incr(redis, stream_id)
    # Presence TTL is armed at INCR time only — re-arm it periodically or a
    # subscriber attached longer than the TTL would silently drop out of the
    # count and voice synthesis would be wrongly skipped mid-run.
    touch_period = settings.background_runs_listener_ttl_seconds / 3
    last_touch = time.monotonic()
    replay_boundary_emitted = False
    orphan_grace = settings.background_runs_orphan_grace_seconds
    last_chunk_at = time.monotonic()
    lock_missing_since: float | None = None
    try:
        async for event in subscribe(redis, stream_id):
            if time.monotonic() - last_touch > touch_period:
                last_touch = time.monotonic()
                with suppress(Exception):
                    await listener_touch(redis, stream_id)
            if not event.is_replay and not replay_boundary_emitted:
                yield ": replay-end\n\n"
                replay_boundary_emitted = True
            if event.kind == "keepalive":
                # D2 remote sign-out: a revoked session closes its subscriber
                # within one keepalive tick (the detached producer continues).
                if not await session_still_valid(session_id):
                    yield SESSION_REVOKED_COMMENT
                    return
                if conversation_id is not None and time.monotonic() - last_chunk_at >= orphan_grace:
                    lock_missing_since, is_orphan = await _probe_orphan(
                        redis, conversation_id, stream_id, lock_missing_since, orphan_grace
                    )
                    if is_orphan:
                        logger.warning(
                            "run_stream_orphan_exit",
                            stream_id=stream_id,
                            conversation_id=conversation_id,
                            grace_seconds=orphan_grace,
                        )
                        sse_streaming_errors_total.labels(
                            error_type="orphaned_run",
                            node_name="run_stream_relay",
                        ).inc()
                        # No replay-end fallback needed here: keepalives are
                        # non-replay events, so the boundary was already
                        # emitted before the first probe could ever run.
                        error_chunk = {
                            "type": "error",
                            FIELD_CONTENT: SSEErrorMessages.run_orphaned(user_language),
                            FIELD_METADATA: {FIELD_ERROR_TYPE: "orphaned_run"},
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                        done_chunk = {
                            "type": "done",
                            FIELD_CONTENT: "",
                            FIELD_METADATA: {
                                "error": True,
                                "orphaned": True,
                                **TokenSummaryDTO.zero().to_metadata(),
                            },
                        }
                        yield f"data: {json.dumps(done_chunk)}\n\n"
                        return
                yield ": heartbeat\n\n"
            elif event.kind == "chunk":
                last_chunk_at = time.monotonic()
                lock_missing_since = None
                if event.is_replay and '"voice_audio_chunk"' in event.payload:
                    # Stale audio is worthless and heavy (base64 MP3) — the
                    # substring pre-filter avoids parsing every replay chunk.
                    with suppress(ValueError):
                        if json.loads(event.payload).get("type") == "voice_audio_chunk":
                            continue
                yield f"data: {event.payload}\n\n"
                if not event.is_replay:
                    # Client pacing applies to LIVE chunks only — a replayed
                    # backlog must flush at full speed (POC-L2-2).
                    await asyncio.sleep(settings.agent_stream_sleep_interval)
            else:  # end
                return
    finally:
        # Best-effort: presence must decay even if the client vanished
        with suppress(Exception):
            await listener_decr(redis, stream_id)


def _build_listener_probe(stream_id: str) -> "Callable[[], Awaitable[bool]]":
    """Async probe: is anyone currently subscribed to this run's stream?

    Injected into stream_chat_response (ADR-117 Lot 2) so voice synthesis
    is skipped when the run executes with no listeners.
    """

    async def _probe() -> bool:
        from src.infrastructure.cache.redis import get_redis_cache
        from src.infrastructure.streaming.run_stream_broker import has_listeners

        return await has_listeners(await get_redis_cache(), stream_id)

    return _probe


def _build_partial_finalizer(conversation_id: str, run_id: str) -> PartialFinalizer:
    """Best-effort archiver for partial assistant content on hard kill.

    Product decision (2026-07): interrupted partial content is KEPT and
    flagged, never silently dropped (billing honesty + context continuity).

    Args:
        conversation_id: Conversation UUID string (owner of the run).
        run_id: Run identifier stored in the row metadata.

    Returns:
        Async callback ``(partial_content, reason) -> None``.
    """

    async def _finalize(partial_content: str, reason: str) -> None:
        import uuid as _uuid

        from src.domains.conversations.service import ConversationService
        from src.infrastructure.database import get_db_context

        conv_service = ConversationService()
        async with get_db_context() as db:
            await conv_service.archive_message(
                _uuid.UUID(conversation_id),
                "assistant",
                partial_content,
                {FIELD_RUN_ID: run_id, "interrupted": True, "interrupt_reason": reason},
                db,
            )

    return _finalize


@router.post("/chat/stream")
async def stream_chat(
    http_request: Request,
    request: ChatRequest,
    current_user: User = Depends(get_current_active_session),
    accept_language: str | None = Header(None, alias="Accept-Language"),
) -> StreamingResponse:
    """
    Stream chat response with Server-Sent Events (SSE).

    Streams:
    - Router decision metadata
    - Response tokens in real-time
    - Heartbeats every 15 seconds (configurable)
    - Final done/error events

    Args:
        http_request: FastAPI Request object for SSE connection monitoring.
        request: ChatRequest with message and session info.
        current_user: Authenticated user from session.
        accept_language: Accept-Language header for i18n (e.g., "fr-FR,fr;q=0.9").

    Returns:
        StreamingResponse with text/event-stream media type.

    Raises:
        HTTPException: If user_id mismatch or other errors.

    SSE Format:
        retry: 5000
        data: {"type": "router_decision", "content": "...", "metadata": {...}}
        : heartbeat
        data: {"type": "token", "content": "Hello", "metadata": null}
        data: {"type": "done", "content": "", "metadata": {"duration_ms": 1234}}

    Example:
        ```bash
        curl -N -H "Cookie: session_id=..." \\
             -X POST http://localhost:8000{API_PREFIX_DEFAULT}/agents/chat/stream \\
             -H "Content-Type: application/json" \\
             -d '{"message": "Hello", "user_id": "...", "session_id": "..."}'
        ```

        Note: API_PREFIX_DEFAULT from constants.py ("/api/v1" by default).
    """
    # Verify user_id matches authenticated user
    if current_user.id != request.user_id:
        raise_user_id_mismatch()

    # D2 remote sign-out: captured at connect time, re-checked at every
    # keepalive tick so a revoked session closes its stream within one tick.
    bff_session_id = http_request.cookies.get(settings.session_cookie_name)

    # === USAGE LIMIT CHECK (Layer 0: HTTP 429 before SSE stream) ===
    # No `usage_limits_enabled` guard: the check also enforces the INSTANCE
    # spend ceiling, a different protection that stays armed when per-user
    # limits are off. It returns early when neither applies.
    from src.domains.usage_limits.schemas import UsageLimitStatus
    from src.domains.usage_limits.service import UsageLimitService
    from src.infrastructure.observability.metrics_usage_limits import (
        usage_limit_enforcement_total,
    )

    _limit_check = await UsageLimitService.check_user_allowed(current_user.id)
    if not _limit_check.allowed:
        usage_limit_enforcement_total.labels(
            layer="router", limit_type=_limit_check.exceeded_limit or "unknown"
        ).inc()
        from src.core.constants import INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
        from src.core.exceptions import raise_usage_limit_exceeded
        from src.domains.usage_limits.instance_budget import (
            seconds_until_next_utc_day,
        )

        _is_instance_pause = _limit_check.status is UsageLimitStatus.BLOCKED_INSTANCE_BUDGET
        raise_usage_limit_exceeded(
            _limit_check.exceeded_limit,
            _limit_check.blocked_reason,
            error_code=INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE if _is_instance_pause else None,
            # The ceiling resets on the UTC day boundary, so "come back
            # tomorrow" is a computable instant rather than a vague hope.
            retry_after_seconds=seconds_until_next_utc_day() if _is_instance_pause else None,
        )
    # === END USAGE LIMIT CHECK ===

    # === ACTIVE-RUN LOCK (ADR-117 Lot 2: HTTP 409 BEFORE the SSE stream) ===
    # One concurrent run per conversation. Acquired here (the SSE generator
    # starts after the 200 status is committed — too late for a 409) and
    # kept alive by the producer's heartbeat; a killed producer frees the
    # conversation in at most background_runs_active_ttl_seconds.
    background_stream_id: str | None = None
    background_conversation_id: str | None = None
    if settings.background_runs_enabled:
        from src.core.exceptions import raise_run_in_progress
        from src.infrastructure.cache import get_conversation_id_cached
        from src.infrastructure.cache.redis import get_redis_cache
        from src.infrastructure.streaming.run_stream_broker import (
            get_active_run,
            register_active_run,
        )

        background_stream_id = generate_run_id()
        background_conversation_id = await get_conversation_id_cached(request.user_id)
        if background_conversation_id:
            _lock_redis = await get_redis_cache()
            acquired = await register_active_run(
                _lock_redis,
                background_conversation_id,
                run_id=background_stream_id,
                stream_id=background_stream_id,
            )
            if not acquired:
                active = await get_active_run(_lock_redis, background_conversation_id)
                logger.info(
                    "chat_run_lock_conflict",
                    user_id=str(current_user.id),
                    conversation_id=background_conversation_id,
                    active_stream_id=(active or {}).get("stream_id"),
                )
                raise_run_in_progress(active)
    # === END ACTIVE-RUN LOCK ===

    logger.info(
        "sse_stream_started",
        user_id=str(current_user.id),
        session_id=request.session_id,
        message_length=len(request.message),
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        """
        Generate SSE events with heartbeats.
        Yields formatted SSE data chunks and periodic heartbeat comments.

        HITL Conversational Routing (Phase 3.3 Unified Architecture):
        - Automatically detects pending HITL in conversation
        - If HITL pending: Calls stream_chat_response(original_run_id=...) for resumption
        - Otherwise: Calls stream_chat_response() for normal flow
        - Uses same entry point for both flows (simplified architecture)
        """
        # NOTE: SSE connection monitoring now done via http_requests_in_progress in PrometheusMiddleware
        # Day 2 / Task 2.3: heartbeats are now driven by `iter_with_keepalive` on the
        # chat stream, so the inline `last_heartbeat` tracker is no longer needed.

        # E2E metrics tracking (PHASE 1.2 - Instrumentation)
        request_start_time = time.time()
        intention_label = "unknown"
        agents_count = 0

        try:
            # Send SSE retry header (client auto-reconnect after 5s)
            yield "retry: 5000\n\n"

            # ✅ HITL CONVERSATIONAL: Check for pending HITL
            # FIX 2026-01-12: Use real conversation UUID from DB, not session_id
            # Bug: session_id (e.g., "session_<user_id>") != conversation.id (UUID)
            # This caused HITL data to be stored with UUID key but searched with session_id key
            #
            # PERF 2026-01-13: Use cached conversation_id to avoid DB query on every request
            # Cache TTL: configurable via CONVERSATION_ID_CACHE_TTL_SECONDS (default: 5 min)
            # Fallback: If cache fails, direct DB query (graceful degradation)
            from src.infrastructure.cache import get_conversation_id_cached

            conversation_id = await get_conversation_id_cached(request.user_id)

            # If no conversation exists yet, skip HITL check (new user, no pending HITL possible)
            if request.hitl_decision is not None and conversation_id:
                # Lot 1 option B: a one-click decision demands an authoritative
                # read — the per-process detection cache (bounded cross-worker
                # staleness) must never misroute a button click.
                pending_hitl = await check_pending_hitl_uncached(conversation_id)
            else:
                pending_hitl = (
                    await check_pending_hitl(conversation_id) if conversation_id else None
                )

            agent_service = get_agent_service()

            if pending_hitl:
                # === PHASE 3.3 DAY 3: Validate pending_hitl is not expired (Layer 2 defense) ===
                # Layer 1 cleanup happens in service.py after HITL completion
                # Layer 2 (here) provides safety net if Layer 1 fails due to exception/crash
                #
                # Why this check:
                # Prevents bug where user sends new message after HITL completion
                # and router misinterprets it as HITL response due to stale pending_hitl
                #
                # Example bug scenario without this check:
                # 1. User: "recherche jean" → HITL interrupt → pending_hitl created
                # 2. User: "ok" → HITL resumption → completion → pending_hitl SHOULD be deleted
                # 3. User: "recherche jean" → Router sees stale pending_hitl → Misroutes to HITL handler
                interrupt_ts_str = pending_hitl.get("interrupt_ts")

                if interrupt_ts_str:
                    from datetime import datetime

                    try:
                        # Parse interrupt timestamp (ISO 8601 format with Z suffix)
                        interrupt_ts_parsed: datetime = datetime.fromisoformat(
                            interrupt_ts_str.replace("Z", "+00:00")
                        )
                        elapsed_seconds = (datetime.now(UTC) - interrupt_ts_parsed).total_seconds()

                        # Check if expired (TTL from settings, default: 3600s = 1h)
                        if elapsed_seconds > settings.hitl_pending_data_ttl_seconds:
                            logger.warning(
                                "pending_hitl_expired_clearing",
                                conversation_id=conversation_id,
                                elapsed_seconds=elapsed_seconds,
                                ttl_seconds=settings.hitl_pending_data_ttl_seconds,
                                user_id=str(current_user.id),
                                reason="TTL exceeded, treating as new message",
                            )

                            # Cleanup expired pending_hitl
                            from src.domains.agents.utils.hitl_store import HITLStore
                            from src.infrastructure.cache.redis import get_redis_cache

                            redis = await get_redis_cache()
                            hitl_store = HITLStore(
                                redis_client=redis,
                                ttl_seconds=settings.hitl_pending_data_ttl_seconds,
                            )
                            # conversation_id is guaranteed non-None here (pending_hitl requires it)
                            if conversation_id:
                                await hitl_store.clear_interrupt(conversation_id)

                            # Clear pending_hitl to route to normal flow
                            pending_hitl = None

                            logger.info(
                                "pending_hitl_expired_cleared_routing_to_normal_flow",
                                conversation_id=conversation_id,
                                user_id=str(current_user.id),
                            )
                    except Exception as expiry_check_error:
                        # Non-fatal: Log error but continue (better to process message than fail)
                        logger.error(
                            "pending_hitl_expiry_check_failed",
                            conversation_id=conversation_id,
                            error=str(expiry_check_error),
                            fallback="Continuing with HITL flow despite expiry check failure",
                        )

            if pending_hitl:
                # === FIX 2026-01-11: Validate pending_hitl has actual content ===
                # Use HITLStore.clear_if_invalid() to handle stale state
                action_requests = pending_hitl.get(FIELD_ACTION_REQUESTS, [])
                if not action_requests:
                    try:
                        from src.domains.agents.utils.hitl_store import HITLStore
                        from src.infrastructure.cache.redis import get_redis_cache

                        redis = await get_redis_cache()
                        hitl_store = HITLStore(
                            redis_client=redis,
                            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
                        )
                        # conversation_id is guaranteed non-None here (pending_hitl requires it)
                        if conversation_id:
                            await hitl_store.clear_if_invalid(conversation_id)
                    except (ConnectionError, TimeoutError, RuntimeError, OSError) as cleanup_err:
                        logger.error(
                            "pending_hitl_invalid_cleanup_failed",
                            error=str(cleanup_err),
                            error_type=type(cleanup_err).__name__,
                        )

                    # Route to normal flow (pending_hitl invalid)
                    pending_hitl = None

                else:
                    # === Valid pending_hitl with action_requests ===
                    # SECURITY: Rate limit HITL responses to prevent spam/abuse
                    # Limit: 10 HITL responses per 60 seconds per user
                    # Prevents malicious users from overwhelming system with repeated approvals
                    from src.core.exceptions import raise_rate_limit_exceeded
                    from src.infrastructure.cache.redis import get_redis_cache

                    redis = await get_redis_cache()
                    rate_key = f"hitl_rate_limit:{current_user.id}"

                    # Increment counter (atomic operation)
                    request_count = await redis.incr(rate_key)

                    if request_count == 1:
                        # First request in window → set TTL
                        await redis.expire(rate_key, HITL_RATE_LIMIT_WINDOW_SECONDS)
                    elif request_count > HITL_RATE_LIMIT_REQUESTS:
                        # Exceeded rate limit
                        logger.warning(
                            "hitl_rate_limit_exceeded",
                            user_id=str(current_user.id),
                            request_count=request_count,
                            window_seconds=HITL_RATE_LIMIT_WINDOW_SECONDS,
                            conversation_id=conversation_id,
                        )

                        # Track security events (dashboards 08 / 16)
                        with suppress(Exception):
                            from src.infrastructure.observability.metrics_agents import (
                                hitl_security_events_total,
                            )
                            from src.infrastructure.observability.metrics_errors import (
                                security_violations_total,
                            )

                            hitl_security_events_total.labels(
                                event_type="rate_limit_exceeded", severity="medium"
                            ).inc()
                            security_violations_total.labels(
                                violation_type="hitl_rate_limit_exceeded"
                            ).inc()

                        # Raised mid-stream: the generator's `except Exception`
                        # converts this into an SSE "error" event (classified
                        # "transient" by SSEErrorMessages) + a "done" chunk —
                        # it never reaches the client as an HTTP 429.
                        raise_rate_limit_exceeded(
                            limit=HITL_RATE_LIMIT_REQUESTS,
                            window_seconds=HITL_RATE_LIMIT_WINDOW_SECONDS,
                            retry_after=HITL_RATE_LIMIT_WINDOW_SECONDS,
                            detail={
                                "error": "rate_limit_exceeded",
                                "message": APIMessages.hitl_rate_limit_exceeded(),
                                "retry_after": HITL_RATE_LIMIT_WINDOW_SECONDS,
                                "limit": HITL_RATE_LIMIT_REQUESTS,
                                "window_seconds": HITL_RATE_LIMIT_WINDOW_SECONDS,
                            },
                            headers={"Retry-After": str(HITL_RATE_LIMIT_WINDOW_SECONDS)},
                        )
                    # Route to HITL response handler
                    # NOTE: conversation_id already retrieved at start of event_generator
                    logger.info(
                        "routing_to_hitl_response_handler",
                        user_id=str(current_user.id),
                        session_id=request.session_id,
                        conversation_id=conversation_id,
                        action_count=len(pending_hitl.get(FIELD_ACTION_REQUESTS, [])),
                    )

                    # Extract run_id from pending_hitl (stored during interrupt)
                    original_run_id = pending_hitl.get(FIELD_RUN_ID)

                    # === PHASE 3.3 DAY 7: Service architecture (migration complete) ===
                    # Uses stream_chat_response() with original_run_id for unified HITL flow
                    # Get user preferences - prioritize stored user.language over Accept-Language header
                    user_timezone = getattr(current_user, "timezone", DEFAULT_USER_DISPLAY_TIMEZONE)
                    user_language = get_user_language(
                        user_language=getattr(current_user, "language", None),
                        accept_language_header=accept_language,
                    )
                    user_display_name = resolve_user_display_name(
                        getattr(current_user, "full_name", None),
                        getattr(current_user, "email", None),
                    )

                    # CRITICAL: Pass original_run_id for token aggregation across HITL invocations
                    # Wrap the chat stream with a concurrent keepalive so SSE comments
                    # (": heartbeat") pulse during long silent phases (eg compaction
                    # LLM call). The legacy post-chunk heartbeat in this block was
                    # blind to in-flight awaits — Day 2 / Task 2.3 replaces it.
                    # ADR-117: billing id (run_id) is REUSED across HITL
                    # interrupt + resumption for token aggregation, but the
                    # transport id (stream_id) MUST be fresh per invocation —
                    # the interrupt phase already wrote a terminal marker on
                    # its own stream, and a replay-from-0 subscriber would
                    # stop at that stale marker. Lot 2: the id was generated
                    # in the endpoint body (the active-run lock is keyed on
                    # it); the fallback covers the flag-OFF-at-body edge.
                    stream_id = background_stream_id or generate_run_id()
                    producer_run_id = original_run_id or stream_id
                    listener_probe = (
                        _build_listener_probe(stream_id)
                        if settings.background_runs_enabled
                        else None
                    )
                    chat_stream = agent_service.stream_chat_response(
                        user_message=request.message,
                        user_id=request.user_id,
                        session_id=request.session_id,
                        user_timezone=user_timezone,
                        user_language=user_language,
                        user_display_name=user_display_name,
                        original_run_id=original_run_id,  # Reuse for token aggregation
                        run_id=producer_run_id,
                        has_listeners=listener_probe,
                        browser_context=request.context,  # Pass browser context (geolocation, etc.)
                        user_memory_enabled=getattr(current_user, "memory_enabled", True),
                        user_journals_enabled=getattr(current_user, "journals_enabled", False),
                        user_psyche_enabled=getattr(current_user, "psyche_enabled", False),
                        user_display_mode=getattr(current_user, "response_display_mode", "cards"),
                        user_execution_mode=getattr(current_user, "execution_mode", "pipeline"),
                        attachment_ids=request.attachment_ids,
                        stt_provider=request.stt_provider,
                        stt_audio_duration_seconds=request.stt_audio_duration_seconds,
                        stt_cost_usd=request.stt_cost_usd,
                        stt_cost_eur=request.stt_cost_eur,
                        hitl_decision=(
                            request.hitl_decision.model_dump() if request.hitl_decision else None
                        ),
                        directive=(request.directive.model_dump() if request.directive else None),
                        client_user_agent=http_request.headers.get("user-agent"),
                    )
                    if settings.background_runs_enabled:
                        # ADR-117: detached execution — the run survives client
                        # disconnects; this endpoint is a mere subscriber.
                        # The e2e duration metric is observed by the producer.
                        spawn_chat_run_producer(
                            chat_stream=chat_stream,
                            run_id=producer_run_id,
                            stream_id=stream_id,
                            user_id=str(current_user.id),
                            session_id=request.session_id,
                            finalize_partial=(
                                _build_partial_finalizer(conversation_id, producer_run_id)
                                if conversation_id
                                else None
                            ),
                            conversation_id=background_conversation_id,
                        )
                        async for sse_line in stream_run_as_sse(
                            stream_id,
                            conversation_id=background_conversation_id,
                            user_language=user_language,
                            session_id=bff_session_id,
                        ):
                            yield sse_line
                    else:
                        async for item in iter_with_keepalive(
                            chat_stream,
                            keepalive_interval_seconds=settings.sse_heartbeat_interval,
                        ):
                            if isinstance(item, KeepalivePulse):
                                if not await session_still_valid(bff_session_id):
                                    yield SESSION_REVOKED_COMMENT
                                    break
                                yield ": heartbeat\n\n"
                                continue

                            chunk = item
                            # E2E metrics: Extract metadata from chunks (PHASE 1.2)
                            if chunk.type == "router_decision" and chunk.metadata:
                                intention_label = chunk.metadata.get("intention", "unknown")

                            # Send chunk as SSE data
                            chunk_json = chunk.model_dump_json()
                            yield f"data: {chunk_json}\n\n"

                            # Small delay
                            await asyncio.sleep(settings.agent_stream_sleep_interval)

            else:
                # Normal flow - no pending HITL
                # Get user timezone from current_user (with fallback to Europe/Paris)
                user_timezone = getattr(current_user, "timezone", DEFAULT_USER_DISPLAY_TIMEZONE)
                # Get user language - prioritize stored user.language over Accept-Language header
                user_language = get_user_language(
                    user_language=getattr(current_user, "language", None),
                    accept_language_header=accept_language,
                )
                user_display_name = resolve_user_display_name(
                    getattr(current_user, "full_name", None),
                    getattr(current_user, "email", None),
                )

                logger.debug(
                    "user_preferences_resolved",
                    user_id=str(current_user.id),
                    user_timezone=user_timezone,
                    user_language=user_language,
                    accept_language_header=accept_language,
                )

                # Lot 1 option B, fail-closed: a one-click decision with no
                # pending interrupt (authoritative read above) is expired or
                # already answered — typed error, never a new LLM turn.
                if request.hitl_decision is not None:
                    logger.warning(
                        "hitl_decision_without_pending_rejected",
                        user_id=str(current_user.id),
                        conversation_id=conversation_id,
                        decision_message_id=request.hitl_decision.message_id,
                    )
                    stale_chunk = ChatStreamChunk(
                        type="error",
                        content=SSEErrorMessages.hitl_decision_stale(language=user_language),
                        metadata={"error_code": "hitl_decision_stale"},
                    )
                    yield f"data: {stale_chunk.model_dump_json()}\n\n"
                    stale_done = ChatStreamChunk(type="done", content="", metadata=None)
                    yield f"data: {stale_done.model_dump_json()}\n\n"
                    return

                # Wrap with concurrent keepalive so heartbeats fire during long
                # silent awaits (Day 2 / Task 2.3) — the legacy inline check
                # only pulsed between received chunks.
                # ADR-117: fresh id per POST — serves as BOTH billing run_id
                # and transport stream_id on the normal (non-HITL) path.
                # Lot 2: generated in the endpoint body (lock key); fallback
                # covers the flag-OFF-at-body edge.
                stream_id = background_stream_id or generate_run_id()
                producer_run_id = stream_id
                listener_probe = (
                    _build_listener_probe(stream_id) if settings.background_runs_enabled else None
                )
                chat_stream = agent_service.stream_chat_response(
                    user_message=request.message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    user_timezone=user_timezone,
                    user_language=user_language,
                    user_display_name=user_display_name,
                    run_id=producer_run_id,
                    has_listeners=listener_probe,
                    browser_context=request.context,  # Pass browser context (geolocation, etc.)
                    user_memory_enabled=getattr(current_user, "memory_enabled", True),
                    user_journals_enabled=getattr(current_user, "journals_enabled", False),
                    user_psyche_enabled=getattr(current_user, "psyche_enabled", False),
                    user_display_mode=getattr(current_user, "response_display_mode", "cards"),
                    user_execution_mode=getattr(current_user, "execution_mode", "pipeline"),
                    attachment_ids=request.attachment_ids,
                    stt_provider=request.stt_provider,
                    stt_audio_duration_seconds=request.stt_audio_duration_seconds,
                    stt_cost_usd=request.stt_cost_usd,
                    stt_cost_eur=request.stt_cost_eur,
                    directive=(request.directive.model_dump() if request.directive else None),
                    client_user_agent=http_request.headers.get("user-agent"),
                )
                if settings.background_runs_enabled:
                    # ADR-117: detached execution — the run survives client
                    # disconnects; this endpoint is a mere subscriber.
                    # The e2e duration metric is observed by the producer.
                    spawn_chat_run_producer(
                        chat_stream=chat_stream,
                        run_id=producer_run_id,
                        stream_id=stream_id,
                        user_id=str(current_user.id),
                        session_id=request.session_id,
                        finalize_partial=(
                            _build_partial_finalizer(conversation_id, producer_run_id)
                            if conversation_id
                            else None
                        ),
                        conversation_id=background_conversation_id,
                    )
                    async for sse_line in stream_run_as_sse(
                        stream_id,
                        conversation_id=background_conversation_id,
                        user_language=user_language,
                        session_id=bff_session_id,
                    ):
                        yield sse_line
                else:
                    async for item in iter_with_keepalive(
                        chat_stream,
                        keepalive_interval_seconds=settings.sse_heartbeat_interval,
                    ):
                        if isinstance(item, KeepalivePulse):
                            if not await session_still_valid(bff_session_id):
                                yield SESSION_REVOKED_COMMENT
                                break
                            yield ": heartbeat\n\n"
                            logger.debug(
                                "sse_heartbeat_sent",
                                user_id=str(current_user.id),
                                session_id=request.session_id,
                            )
                            continue

                        chunk = item
                        # E2E metrics: Extract metadata from chunks (PHASE 1.2)
                        if chunk.type == "router_decision" and chunk.metadata:
                            intention_label = chunk.metadata.get("intention", "unknown")

                        # Send chunk as SSE data
                        chunk_json = chunk.model_dump_json()
                        yield f"data: {chunk_json}\n\n"

                        # Small delay to prevent overwhelming client
                        await asyncio.sleep(settings.agent_stream_sleep_interval)

            # E2E metrics: Record request duration (PHASE 1.2)
            request_duration = time.time() - request_start_time

            # Determine agents bucket classification
            if agents_count == 0 or agents_count == 1:
                agents_bucket = "single"
            elif agents_count <= 3:
                agents_bucket = "few_2-3"
            else:
                agents_bucket = "many_4+"

            e2e_request_duration_with_agents.labels(
                intention=intention_label, agents_bucket=agents_bucket
            ).observe(request_duration)

            logger.info(
                "sse_stream_completed",
                user_id=str(current_user.id),
                session_id=request.session_id,
                duration_seconds=request_duration,
                intention=intention_label,
                agents_count=agents_count,
                agents_bucket=agents_bucket,
            )

        except asyncio.CancelledError:
            logger.info(
                "sse_stream_cancelled",
                user_id=str(current_user.id),
                session_id=request.session_id,
            )
            raise

        except ClientDisconnect:
            # Starlette 0.42+: raised when client disconnects during streaming.
            # This is a graceful termination, not an error.
            logger.info(
                "sse_client_disconnected",
                user_id=str(current_user.id),
                session_id=request.session_id,
                duration_seconds=time.time() - request_start_time,
            )
            return

        except Exception as e:
            # E2E metrics: Record request duration even on error (PHASE 1.2)
            request_duration = time.time() - request_start_time
            agents_bucket = (
                "single" if agents_count <= 1 else "few_2-3" if agents_count <= 3 else "many_4+"
            )

            e2e_request_duration_with_agents.labels(
                intention="error", agents_bucket=agents_bucket
            ).observe(request_duration)

            # PHASE 3.3.1: Track error metrics (was missing - critical gap for Grafana visibility)
            sse_streaming_errors_total.labels(
                error_type=type(e).__name__,
                node_name="router_wrapper",
            ).inc()

            logger.error(
                "sse_stream_error",
                user_id=str(current_user.id),
                session_id=request.session_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=request_duration,
                exc_info=True,
            )

            # Send error event with i18n message (PHASE 3.3.4)
            # Prioritize user's stored language preference over Accept-Language header
            user_language = get_user_language(
                user_language=getattr(current_user, "language", None),
                accept_language_header=accept_language,
            )
            error_message = SSEErrorMessages.stream_error(e, language=user_language)

            error_chunk = {
                "type": "error",
                FIELD_CONTENT: error_message,
                FIELD_METADATA: {FIELD_ERROR_TYPE: "stream_error"},
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"

            # PHASE 3.3.2: Always yield done chunk after error (PHASE 3.1.4 - refactored with DTO)
            zero_summary = TokenSummaryDTO.zero()
            done_chunk = {
                "type": "done",
                FIELD_CONTENT: "",
                FIELD_METADATA: {
                    "error": True,
                    **zero_summary.to_metadata(),  # Clean DTO-based construction
                },
            }
            yield f"data: {json.dumps(done_chunk)}\n\n"

        finally:
            # NOTE: SSE connection monitoring now done via http_requests_in_progress in PrometheusMiddleware
            pass

    # Return StreamingResponse with SSE headers
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",  # Prevent browser caching
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "Connection": "keep-alive",  # Keep connection open
        },
    )


@router.get("/runs/active")
async def get_active_run_status(
    current_user: User = Depends(get_current_active_session),
) -> dict:
    """Report the in-flight background run of the user's conversation, if any.

    ADR-117 Lot 2: polled by the frontend at chat-page mount (and on
    visibility change) to decide whether to reattach to a live stream.
    Read-only — no usage-limit layer, no lock side effects.

    Returns:
        ``{"active": False}`` or
        ``{"active": True, "stream_id": ..., "run_id": ...}``.
    """
    if not settings.background_runs_enabled:
        return {"active": False}

    from src.infrastructure.cache import get_conversation_id_cached
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.streaming.run_stream_broker import get_active_run

    conversation_id = await get_conversation_id_cached(current_user.id)
    if not conversation_id:
        return {"active": False}
    redis = await get_redis_cache()
    active = await get_active_run(redis, conversation_id)
    if not active:
        return {"active": False}
    return {
        "active": True,
        "stream_id": active.get("stream_id"),
        "run_id": active.get("run_id"),
    }


@router.get("/hitl/pending", response_model=PendingHitlResponse | None)
async def get_pending_hitl_interrupt(
    response: Response,
    current_user: User = Depends(get_current_active_session),
) -> PendingHitlResponse | None:
    """Expose the caller's pending HITL interrupt for card rehydration.

    Lot 1 T1.4: the ``hitl_interrupt_metadata`` SSE chunk is not part of the
    archived history — after a page reload, only this Redis-backed state can
    rebuild the approval card. Read-only, scoped to the session user's own
    conversation (no user-supplied id), authoritative Redis read (no
    detection cache), never HTTP-cached.

    Returns:
        The pending interrupt payload, or ``null`` when nothing is pending
        (no conversation yet, answered, expired, or cancelled).
    """
    response.headers["Cache-Control"] = "no-store"

    from src.infrastructure.cache import get_conversation_id_cached

    conversation_id = await get_conversation_id_cached(current_user.id)
    if not conversation_id:
        return None

    pending = await check_pending_hitl_uncached(conversation_id)
    if not pending or not pending.get(FIELD_ACTION_REQUESTS):
        return None

    return PendingHitlResponse(
        message_id=pending.get("message_id"),
        action_requests=pending.get(FIELD_ACTION_REQUESTS, []),
        interrupt_ts=pending.get("interrupt_ts"),
        generated_question=pending.get("generated_question"),
    )


@router.post("/runs/active/cancel")
async def cancel_active_run(
    current_user: User = Depends(get_current_active_session),
) -> dict:
    """Request cancellation of the caller's in-flight background run.

    ADR-117 Lot 3 (stop button). Resolves the caller's OWN conversation's
    active run server-side — no stream id needed from the client, ownership
    is trivially enforced. The producer's cancel watcher (any worker) picks
    the signal up within ``background_runs_cancel_poll_seconds``; the
    partial content is archived flagged ``interrupted`` and subscribers
    receive a synthesized ``done`` chunk with ``metadata.cancelled``.

    Idempotent; already-billed tokens stay billed (no rollback of executed
    tools — cancellation stops what remains, it does not undo the past).

    Returns:
        ``{"cancelled": True, "stream_id": ...}`` when a signal was set,
        ``{"cancelled": False}`` when no run is active (or flag OFF) — the
        frontend then falls back to the legacy local abort.
    """
    if not settings.background_runs_enabled:
        return {"cancelled": False}

    from src.infrastructure.cache import get_conversation_id_cached
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.streaming.run_stream_broker import (
        get_active_run,
        request_cancel,
    )

    conversation_id = await get_conversation_id_cached(current_user.id)
    if not conversation_id:
        return {"cancelled": False}
    redis = await get_redis_cache()
    active = await get_active_run(redis, conversation_id)
    if not active or not active.get("stream_id"):
        return {"cancelled": False}
    stream_id = active["stream_id"]
    await request_cancel(redis, stream_id)
    logger.info(
        "chat_run_cancel_endpoint",
        user_id=str(current_user.id),
        conversation_id=conversation_id,
        stream_id=stream_id,
    )
    return {"cancelled": True, "stream_id": stream_id}


@router.get("/runs/{stream_id}/stream")
async def reattach_run_stream(
    stream_id: str,
    current_user: User = Depends(get_current_active_session),
    lia_session: str | None = Cookie(default=None),
) -> StreamingResponse:
    """Reattach to an in-flight background run (full replay + live tail).

    ADR-117 Lot 2. Ownership: the stream must be the CURRENT active run of
    the caller's own conversation — anything else (finished run, foreign
    stream, unknown id) answers 404 without revealing existence. Finished
    runs are reloaded through the conversation history instead.

    SSE contract: identical to POST /chat/stream (``retry`` hint, ``data:``
    ChatStreamChunk frames, heartbeats), plus the ``: replay-end`` transport
    comment at the replay→live boundary (ignored by parsers that don't
    know it).
    """
    from src.infrastructure.cache import get_conversation_id_cached
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.streaming.run_stream_broker import get_active_run

    if not settings.background_runs_enabled:
        raise_not_found_or_unauthorized("run")

    conversation_id = await get_conversation_id_cached(current_user.id)
    redis = await get_redis_cache()
    active = await get_active_run(redis, conversation_id) if conversation_id else None
    if not active or active.get("stream_id") != stream_id:
        raise_not_found_or_unauthorized("run")

    logger.info(
        "chat_run_reattach",
        user_id=str(current_user.id),
        conversation_id=conversation_id,
        stream_id=stream_id,
    )

    user_language = get_user_language(
        user_language=getattr(current_user, "language", None),
    )

    async def reattach_generator() -> AsyncGenerator[str, None]:
        yield "retry: 5000\n\n"
        async for sse_line in stream_run_as_sse(
            stream_id,
            conversation_id=conversation_id,
            user_language=user_language,
            session_id=lia_session,
        ):
            yield sse_line

    return StreamingResponse(
        reattach_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/health")
async def agents_health() -> dict[str, str | bool]:
    """
    Health check for agents service.

    Returns:
        Status and basic info.
    """
    agent_service = get_agent_service()
    return {
        FIELD_STATUS: "healthy",
        "service": "agents",
        "graph_compiled": agent_service.graph is not None,
    }
