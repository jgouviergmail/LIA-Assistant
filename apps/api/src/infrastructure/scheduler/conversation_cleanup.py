"""Leader sweep of exact retired runtimes, with no transaction across native I/O."""

import time
from datetime import UTC, datetime, timedelta

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_CONVERSATION_CLEANUP
from src.domains.conversations.cleanup_contracts import CleanupState
from src.domains.conversations.cleanup_repository import ConversationCleanupRepository
from src.domains.conversations.cleanup_runner import ConversationCleanupRunner
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.conversation_cleanup_runtime import NativeRuntimeCleanup
from src.infrastructure.database.session import AsyncSessionLocal
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)
from src.infrastructure.observability.metrics_conversation_lifecycle import (
    conversation_cleanup_oldest_timestamp_seconds,
    conversation_cleanup_operations,
    conversation_cleanup_snapshot_timestamp_seconds,
    conversation_executions_recovering,
)

logger = structlog.get_logger(__name__)


async def _publish_inventory() -> None:
    """Publish only a successfully read snapshot, including explicit zeroes."""
    async with AsyncSessionLocal() as db:
        states = await ConversationCleanupRepository(db).outstanding_by_state()
        recovering = await ConversationExecutionRepository(db).recovering_count()
    for state in CleanupState:
        if state == CleanupState.SUCCEEDED:
            continue
        count, oldest = states.get(state, (0, None))
        conversation_cleanup_operations.labels(state=state.value).set(count)
        conversation_cleanup_oldest_timestamp_seconds.labels(state=state.value).set(
            oldest.timestamp() if oldest is not None else 0
        )
    conversation_executions_recovering.set(recovering)
    conversation_cleanup_snapshot_timestamp_seconds.set_to_current_time()


async def cleanup_conversations() -> dict[str, int]:
    """Claim bounded work, count explicit results and retain every unresolved debt."""
    started = time.perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            repo = ConversationCleanupRepository(db)
            identities = await repo.due_ids(limit=settings.conversation_cleanup_batch_size)
            expired = await repo.expire_completed(
                before=datetime.now(UTC)
                - timedelta(days=settings.conversation_cleanup_retention_days)
            )
            await db.commit()
        runner = ConversationCleanupRunner(AsyncSessionLocal, NativeRuntimeCleanup())
        completed = 0
        for identity in identities:
            completed += int(await runner.run_one(operation_id=identity))
        await _publish_inventory()
        deferred = len(identities) - completed
        if deferred:
            background_job_errors_total.labels(job_name=SCHEDULER_JOB_CONVERSATION_CLEANUP).inc(
                deferred
            )
        logger.info(
            "conversation_cleanup_sweep",
            attempted=len(identities),
            completed=completed,
            deferred=deferred,
            expired=expired,
        )
        return {"completed": completed, "deferred": deferred, "expired": expired}
    except Exception as exc:
        background_job_errors_total.labels(job_name=SCHEDULER_JOB_CONVERSATION_CLEANUP).inc()
        logger.warning("conversation_cleanup_sweep_failed", error_type=type(exc).__name__)
        raise
    finally:
        background_job_duration_seconds.labels(job_name=SCHEDULER_JOB_CONVERSATION_CLEANUP).observe(
            time.perf_counter() - started
        )
