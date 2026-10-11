"""Source UI transitions serialize with learning and compare public owned facts."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from pydantic import ConfigDict, JsonValue
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.habits.models import UserHabit
from src.domains.habits.schemas import HabitResponse, HabitStatusUpdate
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


class ManagedHabit(HabitResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    payload: dict[str, JsonValue]


class HabitCompletionUnknown(RuntimeError):
    """A transaction's acknowledgement does not prove its disposition."""


async def managed_habit(
    db: AsyncSession, actor_id: UUID, habit_id: UUID, *, lock: bool = False
) -> ManagedHabit:
    statement = select(*(getattr(UserHabit, name) for name in ManagedHabit.model_fields)).where(
        UserHabit.id == habit_id, UserHabit.user_id == actor_id
    )
    if lock:
        statement = statement.with_for_update()
    row = (await db.execute(statement)).mappings().one_or_none()
    if row is None:
        raise ResourceNotFoundError("habit", str(habit_id))
    return ManagedHabit.model_validate(dict(row))


async def change_managed_habit(
    db: AsyncSession,
    actor_id: UUID,
    habit_id: UUID,
    change: HabitStatusUpdate | None,
    *,
    expected: ManagedHabit | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> ManagedHabit | None:
    """Change status or remove one row; deletion permits future relearning."""
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or not actor.is_active or actor.deleted_at is not None:
        raise AuthorizationError()
    if check is not None:
        await check()
    actual = await compared_habit(db, actor_id, habit_id, expected)
    if change is not None and actual.status.value == change.status:
        if check is not None:
            await check()
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return actual
    statement = (
        delete(UserHabit) if change is None else update(UserHabit).values(status=change.status)
    )
    await db.execute(statement.where(UserHabit.id == habit_id, UserHabit.user_id == actor_id))
    await db.flush()
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise HabitCompletionUnknown() from exc
    if receipt is not None:
        receipt.committed = True
    return (
        None
        if change is None
        else actual.model_copy(update={"status": type(actual.status)(change.status)})
    )


async def compared_habit(
    db: AsyncSession,
    actor_id: UUID,
    habit_id: UUID,
    expected: ManagedHabit | None,
) -> ManagedHabit:
    """Lock and compare the observation; missing approved rows are stale proposals."""
    try:
        actual = await managed_habit(db, actor_id, habit_id, lock=True)
    except ResourceNotFoundError as exc:
        if expected is not None:
            raise ResourceConflictError("habit", detail={"error_code": "STALE_STATE"}) from exc
        raise
    if expected is not None and actual != expected:
        raise ResourceConflictError("habit", detail={"error_code": "STALE_STATE"})
    return actual
