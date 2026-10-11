"""Both Relations UI writes and confirmed assistant commands share one owner lock."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StrictBool, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_user_not_found
from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.users.models import User
from src.domains.users.preference_cas import (
    PreferenceWriteReceipt,
    check_expected_preferences,
    verified_preference_noop,
)
from src.domains.users.repository import UserRepository


class RelationPreferencePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    relation_debrief_enabled: StrictBool | None = None
    relation_overview_scope: RelationOverviewScope | None = None

    @model_validator(mode="after")
    def require_explicit_values(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("At least one explicit non-null relation preference is required")
        return self


class RelationSettingsCompletionUnknown(RuntimeError):
    """SQL commit acknowledgement is unavailable; never claim or retry the effect."""


async def lock_relation_owner(db: AsyncSession, actor_id: UUID) -> User:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    return actor


async def update_relation_preferences(
    db: AsyncSession,
    actor_id: UUID,
    data: RelationPreferencePatch,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> User:
    patch = RelationPreferencePatch.model_validate(data.model_dump(exclude_unset=True))
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
    values = patch.model_dump(mode="json", exclude_unset=True)
    if patch.relation_overview_scope is not None:
        values["relation_overview_scope"] = patch.relation_overview_scope.model_dump(mode="json")
    for name, value in values.items():
        setattr(actor, name, value)
    await db.flush()
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise RelationSettingsCompletionUnknown from exc
    if receipt is not None:
        receipt.committed = True
    return actor
