"""Source UI and confirmed commands share sparse, fresh interest preference writes."""

from collections.abc import Awaitable, Callable, Mapping
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_user_not_found
from src.domains.interests.schemas import InterestSettingsResponse, InterestSettingsUpdate
from src.domains.users.models import User
from src.domains.users.preference_cas import (
    PreferenceWriteReceipt,
    check_expected_preferences,
    verified_preference_noop,
)
from src.domains.users.repository import UserRepository

INTEREST_SETTING_FIELDS = frozenset(InterestSettingsUpdate.model_fields)
if INTEREST_SETTING_FIELDS != set(InterestSettingsResponse.model_fields):
    raise AssertionError("Interest settings read/write declarations must remain complete")


class InterestSettingsCompletionUnknown(RuntimeError):
    """The commit acknowledgement cannot establish whether the write completed."""


async def update_interest_settings(
    db: AsyncSession,
    actor_id: UUID,
    data: InterestSettingsUpdate,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> User:
    parsed = InterestSettingsUpdate.model_validate(data.model_dump(exclude_unset=True))
    patch = InterestSettingsUpdate.model_validate(
        parsed.model_dump(exclude_unset=True, exclude_none=True)
    )
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if check is not None:
        await check()
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    if not patch.model_fields_set:
        return actor
    if expected is not None:
        check_expected_preferences(actor, patch, expected)
    current = {name: getattr(actor, name) for name in patch.model_fields_set}
    if verified_preference_noop(patch, current, receipt):
        return actor
    for name, value in patch.model_dump(exclude_unset=True).items():
        setattr(actor, name, value)
    await db.flush()
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise InterestSettingsCompletionUnknown from exc
    if receipt is not None:
        receipt.committed = True
    return actor
