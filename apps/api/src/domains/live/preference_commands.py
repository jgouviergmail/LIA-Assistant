"""Current locked live preference writes, shared by UI and native confirmation."""

import hashlib
import json
from typing import get_args
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.live.preferences import LivePreferences, read_live_preferences
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.live_preferences import (
    LivePreferenceSnapshot,
    LiveReflexName,
    LiveReflexValues,
)


def defaulted_live_fields(raw: object) -> list[LiveReflexName]:
    defaults: list[LiveReflexName] = []
    for name in get_args(LiveReflexName):
        if not isinstance(raw, dict) or raw.get(name) is None:
            defaults.append(name)
            continue
        try:
            LivePreferences.model_validate({name: raw[name]})
        except ValidationError:
            defaults.append(name)
    return defaults


def live_preference_snapshot(actor: User) -> LivePreferenceSnapshot:
    current = read_live_preferences(actor.live_preferences)
    raw = json.dumps(
        actor.live_preferences,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return LivePreferenceSnapshot(
        values=LiveReflexValues.model_validate(current.model_dump(exclude={"provider"})),
        provider=current.provider,
        stored_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        defaulted_fields=defaulted_live_fields(actor.live_preferences),
    )


async def update_live_preferences(
    db: AsyncSession,
    actor_id: UUID,
    preferences: LivePreferences,
    *,
    expected: LivePreferenceSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> LivePreferences:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    current = live_preference_snapshot(actor)
    if expected is not None and current != expected:
        raise ResourceConflictError("live preferences", detail={"error_code": "STALE_STATE"})
    saved = preferences.model_copy(update={"provider": preferences.provider or current.provider})
    if saved == read_live_preferences(actor.live_preferences):
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return saved
    actor.live_preferences = saved.model_dump()
    db.add(actor)
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return saved
