"""Encrypted, per-account Redis diagnostics, bounded by count AND call age."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from pydantic import JsonValue

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.system_settings.debug_access import can_read_debug
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.llm.jev_debug_models import (
    TRACE_LIMIT,
    TRACE_TTL_SECONDS,
    AppliedVerdict,
    ContextPreview,
    JevAction,
    JevCallTrace,
    JevCollectionCoverage,
    JevTracePage,
    choice_preview,
    context_preview,
)
from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionUsage,
    InvalidResponseReason,
)

logger = structlog.get_logger(__name__)
DEBUG_IO_SECONDS = 0.25

# Pruning and writes are atomic across workers on LIA's Redis instance,
# including updates to the same native attempt.
_PRUNE = """
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
for _, id in ipairs(expired) do
    redis.call('HDEL', KEYS[1], id)
    redis.call('ZREM', KEYS[2], id)
end
local excess = redis.call('ZRANGE', KEYS[2], 0, -(tonumber(ARGV[2]) + 1))
for _, id in ipairs(excess) do
    redis.call('HDEL', KEYS[1], id)
    redis.call('ZREM', KEYS[2], id)
end
"""
_WRITE = (
    """
local previous = redis.call('HGET', KEYS[1], ARGV[4])
-- The clear prefix contains only a finality bit, never diagnostic content.
-- A delayed initial write must not undo the consumer's confirmed action.
if previous and string.sub(previous, 1, 1) == '1' and ARGV[7] == '0' then
    return 0
end
redis.call('HSET', KEYS[1], ARGV[4], ARGV[5])
redis.call('EXPIRE', KEYS[1], ARGV[3])
-- Redis 7.4 (the deployed version): expire each encrypted body even when
-- later calls keep the account's hash alive. HSET clears the previous field TTL.
local deadline = math.floor((tonumber(ARGV[6]) + tonumber(ARGV[3])) * 1000)
redis.call('HPEXPIREAT', KEYS[1], deadline, 'FIELDS', 1, ARGV[4])
redis.call('ZADD', KEYS[2], ARGV[6], ARGV[4])
"""
    + _PRUNE
    + """
redis.call('EXPIRE', KEYS[2], ARGV[3])
return 1
"""
)
_READ = _PRUNE + """
local result = {}
for _, id in ipairs(redis.call('ZREVRANGE', KEYS[2], 0, tonumber(ARGV[2]) - 1)) do
    local value = redis.call('HGET', KEYS[1], id)
    if value then table.insert(result, string.sub(value, 3)) end
end
return result
"""


def trace_keys(user_id: UUID) -> tuple[str, str]:
    prefix = f"debug:jev:{user_id}"
    return f"{prefix}:data", f"{prefix}:index"


async def write_trace(user_id: UUID, trace: JevCallTrace) -> None:
    redis = await get_redis_cache()
    finality = int(trace.action != "pending")
    await redis.eval(
        _WRITE,
        2,
        *trace_keys(user_id),
        datetime.now(UTC).timestamp() - TRACE_TTL_SECONDS,
        TRACE_LIMIT,
        TRACE_TTL_SECONDS,
        str(trace.id),
        f"{finality}:{encrypt_data(trace.model_dump_json())}",
        trace.started_at.timestamp(),
        finality,
    )


async def read_traces(user_id: UUID) -> JevTracePage:
    redis = await get_redis_cache()
    values = await redis.eval(
        _READ,
        2,
        *trace_keys(user_id),
        datetime.now(UTC).timestamp() - TRACE_TTL_SECONDS,
        TRACE_LIMIT,
    )
    return JevTracePage(
        calls=[JevCallTrace.model_validate_json(decrypt_data(value)) for value in values]
    )


async def begin_trace(
    *,
    user_id: UUID,
    usage: JevUsage,
    run_id: str,
    model: str,
    state: JsonValue,
    question: ChoiceQuestion | dict[str, ChoiceQuestion],
) -> JevCallTrace | None:
    """Collect only for an opted-in account; never keep the DB session across HTTP."""
    try:
        async with asyncio.timeout(DEBUG_IO_SECONDS):
            async with get_db_context() as db:
                user = await db.get(User, user_id)
            if user is None or not await can_read_debug(user):
                return None
            return JevCallTrace(
                id=uuid4(),
                run_id=run_id,
                caller=JEV_USAGES[usage].llm_type,
                usage=usage.value,
                started_at=datetime.now(UTC),
                requested_model=model,
                context=context_preview(
                    {
                        "state": state,
                        "question": (
                            question.model_dump()
                            if isinstance(question, ChoiceQuestion)
                            else {key: value.model_dump() for key, value in question.items()}
                        ),
                    }
                ),
            )
    except Exception as exc:
        logger.debug("jev_debug_capture_unavailable", error_type=type(exc).__name__)
        return None


async def save_trace(user_id: UUID, trace: JevCallTrace | None) -> None:
    """Debug failure cannot lose a paid result or trigger a second inference."""
    if trace is None:
        return
    try:
        async with asyncio.timeout(DEBUG_IO_SECONDS):
            await write_trace(user_id, trace)
    except Exception as exc:
        logger.debug("jev_debug_write_unavailable", error_type=type(exc).__name__)


async def record_action(
    user_id: UUID,
    trace: JevCallTrace | None,
    *,
    action: JevAction,
    outcome: str,
    target: str | None = None,
    applied_decisions: dict[str, AppliedVerdict] | None = None,
    decision_labels: dict[str, str] | None = None,
    observed_result: ContextPreview | None = None,
    collection_coverage: JevCollectionCoverage | None = None,
) -> None:
    if trace is not None:
        await save_trace(
            user_id,
            trace.model_copy(
                update={
                    "action": action,
                    "outcome": outcome,
                    "action_target": target[:240] if target else None,
                    "observed_result": observed_result,
                    "collection_coverage": collection_coverage or trace.collection_coverage,
                    "applied_decisions": applied_decisions or {},
                    "decision_labels": {
                        key[:100]: value[:180]
                        for key, value in list((decision_labels or {}).items())[:24]
                    },
                }
            ),
        )


async def finish_trace(
    user_id: UUID,
    trace: JevCallTrace | None,
    *,
    answer: ChoiceAnswer | dict[str, ChoiceAnswer] | None,
    question: ChoiceQuestion | dict[str, ChoiceQuestion],
    reported_model: str | None,
    duration_ms: float,
    outcome: str,
    action: JevAction,
    status_code: int | None,
    counters: DecisionUsage | None,
    cost_eur: float | None,
    invalid_response_reason: InvalidResponseReason | None = None,
) -> JevCallTrace | None:
    """Record the call even if accounting or its consumer subsequently fails."""
    if trace is None:
        return None
    try:
        completed = trace.model_copy(
            update={
                "reported_model": reported_model,
                "duration_ms": duration_ms,
                "response": (
                    choice_preview(answer, question)
                    if isinstance(answer, ChoiceAnswer) and isinstance(question, ChoiceQuestion)
                    else None
                ),
                "responses": (
                    {
                        key: choice_preview(value, question[key], limit=3)
                        for key, value in answer.items()
                    }
                    if isinstance(answer, dict) and isinstance(question, dict)
                    else {}
                ),
                "outcome": outcome,
                "invalid_response_reason": invalid_response_reason,
                "action": action,
                "status_code": status_code,
                "input_tokens": counters.input_tokens if counters else None,
                "output_tokens": counters.output_tokens if counters else None,
                "cost_eur": cost_eur,
            }
        )
        await save_trace(user_id, completed)
        return completed
    except Exception as exc:
        logger.debug("jev_debug_format_unavailable", error_type=type(exc).__name__)
        return None
