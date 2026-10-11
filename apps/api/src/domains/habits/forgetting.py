"""The UI and assistant erase the same owned persistent and advisory habit state."""

from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.habits.forget_snapshot import HabitForgetSnapshot, habit_forget_snapshot
from src.domains.habits.management_commands import HabitCompletionUnknown
from src.domains.habits.models import UserActivityDay, UserHabit, UserHabitProfile
from src.domains.habits.schemas import HabitsDeleteAllResponse
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository

logger = structlog.get_logger(__name__)


async def clear_habit_advisory_state(actor_id: UUID) -> bool:
    """Preserve both source cleanup attempts and state when completion is unconfirmed."""
    from src.domains.habits.presence import forget_user
    from src.infrastructure.cache import recurrence_store
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
    except Exception as exc:
        logger.warning("habits_advisory_cleanup_unavailable", exception_type=type(exc).__name__)
        return False
    complete = True
    for cleanup in (recurrence_store.delete_user_ledger, forget_user):
        try:
            await cleanup(redis, str(actor_id))
        except Exception as exc:
            logger.warning("habits_advisory_cleanup_failed", exception_type=type(exc).__name__)
            complete = False
    return complete


async def forget_habit_data(
    db: AsyncSession,
    actor_id: UUID,
    *,
    expected: HabitForgetSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> HabitsDeleteAllResponse:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or not actor.is_active or actor.deleted_at is not None:
        raise AuthorizationError()
    if check is not None:
        await check()
    actual = await habit_forget_snapshot(db, actor_id, locked=True)
    if expected is not None and actual != expected:
        raise ResourceConflictError("habits", detail={"error_code": "STALE_STATE"})
    for model in (UserHabit, UserHabitProfile, UserActivityDay):
        await db.execute(delete(model).where(model.user_id == actor_id))
    await db.flush()
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise HabitCompletionUnknown() from exc
    result = HabitsDeleteAllResponse(
        deleted_habits=actual.habits,
        profile_deleted=True,
        deleted_activity_days=actual.activity_days,
        advisory_cleanup_confirmed=False,
    )
    if receipt is not None:
        receipt.committed, receipt.values = True, result.model_dump(mode="json")
    if check is not None:
        await check()
    cleaned = await clear_habit_advisory_state(actor_id)
    result = result.model_copy(update={"advisory_cleanup_confirmed": cleaned})
    if receipt is not None:
        receipt.values = result.model_dump(mode="json")
    return result
