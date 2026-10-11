"""The normal UI and native assistant run the same explicit source recompute."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.habits.management_commands import HabitCompletionUnknown
from src.domains.habits.overview_projection import profile_to_schema
from src.domains.habits.schemas import HabitsRecomputeResponse
from src.domains.habits.service import HabitsService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


async def recompute_managed_habits(
    db: AsyncSession,
    actor_id: UUID,
    *,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> HabitsRecomputeResponse:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or not actor.is_active or actor.deleted_at is not None:
        raise AuthorizationError()
    if check is not None:
        await check()
    service = HabitsService(db)
    outcome = await service.recompute_user_profile(actor, force=True)
    await db.flush()
    profile = await service.repository.get_profile(actor_id)
    result = HabitsRecomputeResponse(outcome=outcome, profile=profile_to_schema(profile))
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise HabitCompletionUnknown() from exc
    if receipt is not None:
        receipt.committed, receipt.values = True, result.model_dump(mode="json")
    return result
