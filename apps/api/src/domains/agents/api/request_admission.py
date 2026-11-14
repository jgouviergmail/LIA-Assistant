"""Validate a browser turn and commit its authority before any SSE header leaves."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from src.core.config import settings
from src.core.constants import (
    HITL_RATE_LIMIT_REQUESTS,
    HITL_RATE_LIMIT_WINDOW_SECONDS,
    REDIS_KEY_HITL_RATE_LIMIT_PREFIX,
)
from src.core.conversation_execution import RunAdmission, RunBusy
from src.core.conversation_selection import ConversationSelection
from src.core.exceptions import raise_rate_limit_exceeded, raise_run_in_progress
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.api.hitl_pending import pending_run_id
from src.domains.agents.api.run_schemas import ActiveRunResponse
from src.domains.agents.utils import generate_run_id
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics_agents import hitl_security_events_total
from src.infrastructure.observability.metrics_errors import security_violations_total
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter
from src.infrastructure.streaming.live_binding import delegated_target
from src.infrastructure.streaming.run_admission import (
    release_unstarted_execution,
    reserve_execution,
)


@dataclass(frozen=True, slots=True)
class PreparedChat:
    """A committed claim, and the existing billing run if this answers a question."""

    admission: RunAdmission
    original_run_id: str | None


def public_busy(busy: RunBusy, title: str | None) -> dict[str, object]:
    """Expose only owner-visible coordinates; private runtime authority never leaves."""
    return ActiveRunResponse.occupied(busy, title).model_dump(
        mode="json", exclude={"active", "selected"}
    )


async def prepare_chat(
    owner_id: UUID, selection: ConversationSelection, *, live_session_id: str | None = None
) -> PreparedChat:
    """Admit once, then read this runtime's question strictly and retag billing.

    A read failure or cancellation closes only this unused admission. No Redis
    lease or absent cached Main may bypass the durable account-wide slot.
    """
    if live_session_id is not None:
        target = await delegated_target(owner_id, live_session_id, selection)
    else:
        async with get_db_context() as db:
            resolved = await ConversationCatalogueService(db).resolve_target(
                owner_id,
                selection,
                create_primary=True,
            )
        assert resolved is not None
        target = resolved
    stream_id = generate_run_id()
    result = await reserve_execution(
        target,
        run_id=stream_id,
        stream_id=stream_id,
        relayed=settings.background_runs_enabled,
        cancellable=True,
    )
    if isinstance(result, RunBusy):
        async with get_db_context() as db:
            row = await ConversationCatalogueService(db).require_owned(owner_id, result.target.id)
            title = row.title
        raise_run_in_progress(public_busy(result, title))
    try:
        original_run_id = await _pending_run(result)
        if original_run_id is not None:
            async with get_db_context() as db:
                resumed = await ConversationExecutionRepository(db).retag_run(
                    result, original_run_id
                )
            result = resumed
        return PreparedChat(result, original_run_id)
    except Exception, asyncio.CancelledError:
        await finish_owned_task(asyncio.create_task(release_unstarted_execution(result)))
        raise


async def _pending_run(admission: RunAdmission) -> str | None:
    """A malformed or unreadable approval must never become an ordinary new turn."""
    run_id = await pending_run_id(str(admission.target.runtime_id))
    if run_id is not None:
        await _limit_answers(admission.target.owner_id)
    return run_id


async def _limit_answers(owner_id: UUID) -> None:
    """Use the existing atomic limiter, apart from the legacy integer counter."""
    limiter = RedisRateLimiter(await get_redis_cache())
    if await limiter.acquire(
        f"{REDIS_KEY_HITL_RATE_LIMIT_PREFIX}{owner_id}:sliding",
        HITL_RATE_LIMIT_REQUESTS,
        HITL_RATE_LIMIT_WINDOW_SECONDS,
        fail_open=False,
    ):
        return
    hitl_security_events_total.labels(event_type="rate_limit_exceeded", severity="medium").inc()
    security_violations_total.labels(violation_type="hitl_rate_limit_exceeded").inc()
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
