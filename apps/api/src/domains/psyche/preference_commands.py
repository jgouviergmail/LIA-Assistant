"""UI and confirmed native settings share a fresh, sparse owner transaction."""

from collections.abc import Awaitable, Callable, Mapping
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_user_not_found
from src.domains.psyche.schemas import PsycheSettingsUpdate
from src.domains.users.models import User
from src.domains.users.preference_cas import (
    PreferenceWriteReceipt,
    check_expected_preferences,
    verified_preference_noop,
)
from src.domains.users.repository import UserRepository

PSYCHE_SETTING_FIELDS = frozenset(PsycheSettingsUpdate.model_fields)


class PsycheSettingsCompletionUnknown(RuntimeError):
    """Commit acknowledgement does not establish the result."""


async def update_psyche_preferences(
    db: AsyncSession,
    actor_id: UUID,
    data: PsycheSettingsUpdate,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> User:
    patch = PsycheSettingsUpdate.model_validate(data.model_dump(exclude_unset=True))
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if check is not None:
        await check()
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
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
        raise PsycheSettingsCompletionUnknown from exc
    if receipt is not None:
        receipt.committed = True
    return actor
