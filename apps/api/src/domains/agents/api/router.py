"""
Agents domain router.
FastAPI endpoints for chat with SSE streaming.
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from src.core.config import settings
from src.core.constants import HITL_RATE_LIMIT_REQUESTS, HITL_RATE_LIMIT_WINDOW_SECONDS
from src.core.exceptions import raise_user_id_mismatch
from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_CONTENT,
    FIELD_ERROR_TYPE,
    FIELD_METADATA,
    FIELD_RUN_ID,
    FIELD_STATUS,
)
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_hitl import get_user_language
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.api.error_messages import SSEErrorMessages
from src.domains.agents.api.schemas import ChatRequest
from src.domains.agents.api.service import AgentService
from src.domains.auth.models import User
from src.domains.chat.schemas import TokenSummaryDTO
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    e2e_request_duration_with_agents,
    sse_streaming_errors_total,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# Global service instance (singleton) - Thread-safe lazy initialization
_agent_service: AgentService | None = None
_agent_service_lock = threading.Lock()

# PHASE 8.1.3: In-memory LRU cache for HITL pending checks (performance optimization)
# Trade-off: 5-second stale data risk vs -10-20ms latency per request

_hitl_cache: dict[str, tuple[dict | None, datetime]] = {}
HITL_CACHE_TTL = timedelta(seconds=5)  # Short TTL for freshness


def invalidate_hitl_cache(conversation_id: str) -> None:
    """
    Invalidate the in-memory HITL cache for a specific conversation.

    Called after clearing HITL state from Redis to ensure cache consistency.
    Prevents stale cache data from causing routing issues when a new request
    arrives shortly after HITL completion/cancellation.

    Args:
        conversation_id: Conversation UUID string to invalidate.
    """
    global _hitl_cache

    if conversation_id in _hitl_cache:
        del _hitl_cache[conversation_id]
        logger.debug(
            "hitl_cache_invalidated",
            conversation_id=conversation_id,
        )


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


async def _check_pending_hitl_uncached(conversation_id: str) -> dict | None:
    """
    Check if conversation has pending HITL interrupt (uncached Redis query).

    Detects if the conversation has a pending HITL interrupt stored in Redis
    waiting for user response. This is used to automatically pass original_run_id
    to stream_chat_response() for unified HITL resumption flow.

    Detection strategy:
    - Check Redis for hitl_pending:{conversation_id} key using HITLStore
    - If found, return action_requests, metadata, and interrupt_ts for routing
    - If not found, no pending HITL (normal flow)

    Args:
        conversation_id: Conversation UUID string.

    Returns:
        dict with action_requests, review_configs, and interrupt_ts if HITL pending, None otherwise.

    Note:
        This function queries Redis for pending HITL state with schema versioning.
        Internal implementation - use _check_pending_hitl() wrapper for caching.
    """
    from src.domains.agents.utils import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    logger.debug(
        "checking_pending_hitl_uncached",
        conversation_id=conversation_id,
    )

    try:
        redis = await get_redis_cache()
        hitl_store = HITLStore(
            redis_client=redis,
            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
        )

        versioned_data = await hitl_store.get_interrupt(conversation_id)

        logger.debug(
            "pending_hitl_check_result_uncached",
            conversation_id=conversation_id,
            found=bool(versioned_data),
        )

        if versioned_data:
            # Extract interrupt_data and interrupt_ts from versioned structure
            interrupt_data = versioned_data.get("interrupt_data", {})
            interrupt_ts = versioned_data.get("interrupt_ts")

            # Return flattened structure for backward compatibility + interrupt_ts
            result = {
                **interrupt_data,
                "interrupt_ts": interrupt_ts,  # Add for response time metric
            }

            logger.info(
                "pending_hitl_detected",
                conversation_id=conversation_id,
                action_count=len(result.get("action_requests", [])),
                interrupt_ts=interrupt_ts,
            )
            return result

    except Exception as e:
        logger.error(
            "check_pending_hitl_error",
            conversation_id=conversation_id,
            error=str(e),
        )

    return None


async def _check_pending_hitl(conversation_id: str) -> dict | None:
    """
    Check if conversation has pending HITL interrupt (with 5-second in-memory cache).

    PHASE 8.1.3 Performance Optimization:
    - Caches Redis lookups for 5 seconds in-memory
    - Trade-off: 5-second stale data risk vs -10-20ms latency
    - Cache hit rate expected: ~50-70% (rapid user responses)

    Args:
        conversation_id: Conversation UUID string.

    Returns:
        dict with action_requests, review_configs, and interrupt_ts if HITL pending, None otherwise.
    """
    global _hitl_cache

    now = datetime.now()

    # Cache hit (fresh data)
    if conversation_id in _hitl_cache:
        data, cached_at = _hitl_cache[conversation_id]
        if now - cached_at < HITL_CACHE_TTL:
            logger.debug(
                "hitl_cache_hit",
                conversation_id=conversation_id,
                age_seconds=(now - cached_at).total_seconds(),
            )
            return data

    # Cache miss or stale → fetch from Redis
    logger.debug("hitl_cache_miss", conversation_id=conversation_id)
    data = await _check_pending_hitl_uncached(conversation_id)

    # Update cache
    _hitl_cache[conversation_id] = (data, now)

    # Cleanup old cache entries (prevent memory leak)
    # Remove entries older than 2x TTL
    cleanup_threshold = now - (HITL_CACHE_TTL * 2)
    _hitl_cache = {
        conv_id: (d, ts) for conv_id, (d, ts) in _hitl_cache.items() if ts > cleanup_threshold
    }

    return data


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

    # === USAGE LIMIT CHECK (Layer 0: HTTP 429 before SSE stream) ===
    if getattr(settings, "usage_limits_enabled", False):
        from src.domains.usage_limits.service import UsageLimitService
        from src.infrastructure.observability.metrics_usage_limits import (
            usage_limit_enforcement_total,
        )

        _limit_check = await UsageLimitService.check_user_allowed(current_user.id)
        if not _limit_check.allowed:
            usage_limit_enforcement_total.labels(
                layer="router", limit_type=_limit_check.exceeded_limit or "unknown"
            ).inc()
            from src.core.exceptions import raise_usage_limit_exceeded

            raise_usage_limit_exceeded(_limit_check.exceeded_limit, _limit_check.blocked_reason)
    # === END USAGE LIMIT CHECK ===

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
        last_heartbeat = time.time()

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
            pending_hitl = await _check_pending_hitl(conversation_id) if conversation_id else None

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
                    from fastapi import HTTPException, status

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
                        try:
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
                        except Exception:
                            pass

                        # Raise HTTP 429 with Retry-After header
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
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
                    user_timezone = getattr(current_user, "timezone", "Europe/Paris")
                    user_language = get_user_language(
                        user_language=getattr(current_user, "language", None),
                        accept_language_header=accept_language,
                    )

                    # CRITICAL: Pass original_run_id for token aggregation across HITL invocations
                    async for chunk in agent_service.stream_chat_response(
                        user_message=request.message,
                        user_id=request.user_id,
                        session_id=request.session_id,
                        user_timezone=user_timezone,
                        user_language=user_language,
                        original_run_id=original_run_id,  # Reuse for token aggregation
                        browser_context=request.context,  # Pass browser context (geolocation, etc.)
                        user_memory_enabled=getattr(current_user, "memory_enabled", True),
                        user_journals_enabled=getattr(current_user, "journals_enabled", False),
                        user_psyche_enabled=getattr(current_user, "psyche_enabled", False),
                        user_display_mode=getattr(current_user, "response_display_mode", "cards"),
                        user_execution_mode=getattr(current_user, "execution_mode", "pipeline"),
                        attachment_ids=request.attachment_ids,
                    ):
                        # E2E metrics: Extract metadata from chunks (PHASE 1.2)
                        if chunk.type == "router_decision" and chunk.metadata:
                            intention_label = chunk.metadata.get("intention", "unknown")
                        elif chunk.type == "planner_metadata" and chunk.metadata:
                            # Extract agents count from planner
                            agents_list = chunk.metadata.get("agents", [])
                            agents_count = len(agents_list) if agents_list else 0

                        # Send chunk as SSE data
                        chunk_json = chunk.model_dump_json()
                        yield f"data: {chunk_json}\n\n"

                        # Send heartbeat if needed
                        current_time = time.time()
                        if current_time - last_heartbeat > settings.sse_heartbeat_interval:
                            yield ": heartbeat\n\n"
                            last_heartbeat = current_time

                        # Small delay
                        await asyncio.sleep(settings.agent_stream_sleep_interval)

            else:
                # Normal flow - no pending HITL
                # Get user timezone from current_user (with fallback to Europe/Paris)
                user_timezone = getattr(current_user, "timezone", "Europe/Paris")
                # Get user language - prioritize stored user.language over Accept-Language header
                user_language = get_user_language(
                    user_language=getattr(current_user, "language", None),
                    accept_language_header=accept_language,
                )

                logger.debug(
                    "user_preferences_resolved",
                    user_id=str(current_user.id),
                    user_timezone=user_timezone,
                    user_language=user_language,
                    accept_language_header=accept_language,
                )

                async for chunk in agent_service.stream_chat_response(
                    user_message=request.message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    user_timezone=user_timezone,
                    user_language=user_language,
                    browser_context=request.context,  # Pass browser context (geolocation, etc.)
                    user_memory_enabled=getattr(current_user, "memory_enabled", True),
                    user_journals_enabled=getattr(current_user, "journals_enabled", False),
                    user_psyche_enabled=getattr(current_user, "psyche_enabled", False),
                    user_display_mode=getattr(current_user, "response_display_mode", "cards"),
                    user_execution_mode=getattr(current_user, "execution_mode", "pipeline"),
                    attachment_ids=request.attachment_ids,
                ):
                    # E2E metrics: Extract metadata from chunks (PHASE 1.2)
                    if chunk.type == "router_decision" and chunk.metadata:
                        intention_label = chunk.metadata.get("intention", "unknown")
                    elif chunk.type == "planner_metadata" and chunk.metadata:
                        # Extract agents count from planner
                        agents_list = chunk.metadata.get("agents", [])
                        agents_count = len(agents_list) if agents_list else 0

                    # Send chunk as SSE data
                    chunk_json = chunk.model_dump_json()
                    yield f"data: {chunk_json}\n\n"

                    # Send heartbeat if needed (prevent timeout)
                    current_time = time.time()
                    if current_time - last_heartbeat > settings.sse_heartbeat_interval:
                        yield ": heartbeat\n\n"
                        last_heartbeat = current_time
                        # NOTE: Heartbeat metric removed - SSE streams are short-lived, no need to track

                        logger.debug(
                            "sse_heartbeat_sent",
                            user_id=str(current_user.id),
                            session_id=request.session_id,
                        )

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
