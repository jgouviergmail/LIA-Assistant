"""Pending-HITL interrupt detection for the agents chat endpoint.

Extracted from ``router.py`` (Lot 1) so the detection helpers live with the
in-memory cache they use (``utils.hitl_cache``) rather than swelling the
route module. Two entry points:

- :func:`check_pending_hitl_uncached` — authoritative Redis read. Used by the
  one-click decision path and the ``GET /agents/hitl/pending`` rehydration
  endpoint, where a stale cache read must never misroute a button click.
- :func:`check_pending_hitl` — cache-fronted read for the hot chat path;
  ``HITLStore.save/delete`` invalidate the entry at the source, so
  same-process staleness is impossible and the TTL only bounds cross-worker
  staleness.
"""

from __future__ import annotations

from src.core.config import settings
from src.core.constants import CONVERSATION_RUN_ID_MAX_LENGTH
from src.core.conversation_target import ConversationRef
from src.core.exceptions import CacheError
from src.core.field_names import FIELD_ACTION_REQUESTS, FIELD_RUN_ID
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.core.stream_codes import HITL_DECISION_STALE_ERROR_CODE as HITL_DECISION_STALE_ERROR_CODE
from src.domains.agents.api.error_messages import SSEErrorMessages
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.utils import hitl_cache
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def pending_run_id(runtime_id: str) -> str | None:
    """Read a valid pending run strictly; unknown state never becomes a fresh turn.

    Args:
        runtime_id: The frozen generation, never its business discussion id.

    Raises:
        CacheError: Redis is unavailable or the question has invalid coordinates.
    """
    pending = await check_pending_hitl_uncached(runtime_id, raise_on_error=True)
    if pending is None:
        return None
    run_id = pending.get(FIELD_RUN_ID)
    if (
        not pending.get(FIELD_ACTION_REQUESTS)
        or not isinstance(run_id, str)
        or not run_id
        or len(run_id) > CONVERSATION_RUN_ID_MAX_LENGTH
        or "\x00" in run_id
    ):
        raise CacheError(operation="hitl_pending", detail=APIMessages.service_unavailable("Redis"))
    return run_id


def extract_decision_type(resume_data: object) -> str:
    """HITL decision label from interrupt resume data, defaulting to ``UNKNOWN``.

    Kept as a module helper so the branch stays out of the streaming
    orchestrator's cyclomatic-complexity budget (audit F015).
    """
    if isinstance(resume_data, dict):
        return str(resume_data.get("decision", "UNKNOWN"))
    return "UNKNOWN"


def hitl_stale_chunks(user_language: str) -> list[ChatStreamChunk]:
    """Typed error + done chunks for a stale one-click HITL decision (Lot 1).

    Fail-closed: the frontend card flips to its ``expired`` state and the
    message is never processed as a new turn. Lives here (not in the streaming
    service) to keep that frozen module under its size cap.
    """
    return [
        ChatStreamChunk(
            type="error",
            content=SSEErrorMessages.hitl_decision_stale(
                language=normalize_language(user_language)
            ),
            metadata={"error_code": HITL_DECISION_STALE_ERROR_CODE},
        ),
        ChatStreamChunk(type="done", content="", metadata=None),
    ]


async def check_pending_hitl_uncached(
    conversation_id: str, *, raise_on_error: bool = False
) -> dict | None:
    """Check for a pending HITL interrupt with an authoritative Redis read.

    Detects whether the conversation has a pending HITL interrupt stored in
    Redis awaiting a user response. Returns the flattened interrupt payload
    (action_requests + interrupt_ts and, for newer interrupts, message_id)
    or None. Routing guards fail open by default; the card endpoint requests
    a strict read so an outage cannot be mistaken for an answered question.

    Args:
        conversation_id: Conversation UUID string.

    Returns:
        The flattened interrupt dict if pending, else None.
    """
    from src.domains.agents.utils import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    logger.debug("checking_pending_hitl_uncached", conversation_id=conversation_id)

    try:
        redis = await get_redis_cache()
        hitl_store = HITLStore(
            redis_client=redis,
            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
        )

        # The one flattened shape every door that resumes a question reads.
        result = await hitl_store.get_pending(conversation_id)

        logger.debug(
            "pending_hitl_check_result_uncached",
            conversation_id=conversation_id,
            found=bool(result),
        )

        if result:
            logger.info(
                "pending_hitl_detected",
                conversation_id=conversation_id,
                action_count=len(result.get("action_requests", [])),
                interrupt_ts=result.get("interrupt_ts"),
            )
            return result

    except Exception as e:  # noqa: BLE001 — graceful degradation, logged
        logger.error(
            "check_pending_hitl_error",
            conversation_id=conversation_id,
            error_type=type(e).__name__,
        )
        if raise_on_error:
            raise CacheError(
                operation="hitl_pending",
                detail=APIMessages.service_unavailable("Redis"),
            ) from e

    return None


async def check_pending_hitl(conversation_id: str) -> dict | None:
    """Cache-fronted pending-HITL detection for the hot chat path.

    PHASE 8.1.3 optimization. ``HITLStore.save_interrupt``/``delete_interrupt``
    invalidate the entry at the source, so same-process staleness is
    impossible; the TTL only bounds cross-worker staleness.

    Args:
        conversation_id: Conversation UUID string.

    Returns:
        The flattened interrupt dict if pending, else None.
    """
    hit, data = hitl_cache.get_cached(conversation_id)
    if hit:
        logger.debug("hitl_cache_hit", conversation_id=conversation_id)
        return data

    logger.debug("hitl_cache_miss", conversation_id=conversation_id)
    data = await check_pending_hitl_uncached(conversation_id)
    hitl_cache.set_cached(conversation_id, data)
    return data


async def clear_completed_interrupt(target: ConversationRef) -> None:
    """Consume a completed continuation under its still-admitted runtime authority.

    The caller invokes this only when no replacement question was produced.
    A failure is propagated; it is never logged as successful cleanup.
    """
    from src.domains.agents.utils import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    store = HITLStore(await get_redis_cache(), settings.hitl_pending_data_ttl_seconds)
    await store.clear_interrupt(str(target.runtime_id))
