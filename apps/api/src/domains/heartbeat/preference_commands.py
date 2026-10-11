"""Shared, canonical heartbeat preference writes for the UI and confirmed commands."""

import json
from collections.abc import Iterable, Mapping
from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, raise_user_not_found
from src.domains.heartbeat.schemas import HeartbeatSettingsResponse, HeartbeatSettingsUpdate
from src.domains.heartbeat.source_policy import (
    HEARTBEAT_SOURCE_DEPENDENCIES,
    HEARTBEAT_SOURCE_ORDER,
    disabled_sources_for,
    sanitize_disabled_sources,
)
from src.domains.moments.preferences import (
    MOMENT_KIND_ORDER,
    disabled_kinds_for,
    sanitize_disabled_kinds,
    unmet_kind_dependencies,
)
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository

HEARTBEAT_PREFERENCE_FIELDS = frozenset(
    {
        "heartbeat_enabled",
        "heartbeat_notify_start_hour",
        "heartbeat_notify_end_hour",
        "heartbeat_disabled_sources",
        "moment_kinds_disabled",
    }
)
_VALUES: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


def heartbeat_settings_response(
    user: User, available_sources: list[str]
) -> HeartbeatSettingsResponse:
    """The UI and assistant read one projection, including current source dependencies."""
    return HeartbeatSettingsResponse(
        heartbeat_enabled=user.heartbeat_enabled,
        heartbeat_notify_start_hour=user.heartbeat_notify_start_hour,
        heartbeat_notify_end_hour=user.heartbeat_notify_end_hour,
        available_sources=available_sources,
        disabled_sources=sorted(disabled_sources_for(user)),
        all_sources=list(HEARTBEAT_SOURCE_ORDER),
        source_dependencies={k: list(v) for k, v in HEARTBEAT_SOURCE_DEPENDENCIES.items()},
        moment_kinds_disabled=sorted(disabled_kinds_for(user)),
        all_moment_kinds=list(MOMENT_KIND_ORDER),
        moment_kind_dependencies={
            kind: list(requires)
            for kind, requires in unmet_kind_dependencies(
                available=frozenset(available_sources)
            ).items()
        },
    )


def assert_heartbeat_preference_coverage() -> None:
    if set(HeartbeatSettingsUpdate.model_fields) != HEARTBEAT_PREFERENCE_FIELDS:
        raise AssertionError("New heartbeat preference fields require explicit operation review")


def normalize_heartbeat_patch(data: HeartbeatSettingsUpdate) -> dict[str, JsonValue]:
    data = HeartbeatSettingsUpdate.model_validate(data)
    # The HTTP schema declares null as an omitted partial update; [] is a clear.
    values: dict[str, object] = data.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    if data.heartbeat_disabled_sources is not None:
        values["heartbeat_disabled_sources"] = sanitize_disabled_sources(
            data.heartbeat_disabled_sources
        )
    if data.moment_kinds_disabled is not None:
        values["moment_kinds_disabled"] = sanitize_disabled_kinds(data.moment_kinds_disabled)
    return _VALUES.validate_python(values)


def heartbeat_preference_values(user: User, fields: Iterable[str]) -> dict[str, JsonValue]:
    names = set(fields)
    if not names <= HEARTBEAT_PREFERENCE_FIELDS:
        raise ValueError("Unknown heartbeat preference field")
    values: dict[str, object] = {name: getattr(user, name) for name in sorted(names)}
    if "heartbeat_disabled_sources" in names:
        values["heartbeat_disabled_sources"] = sorted(disabled_sources_for(user))
    if "moment_kinds_disabled" in names:
        values["moment_kinds_disabled"] = sanitize_disabled_kinds(list(disabled_kinds_for(user)))
    return _VALUES.validate_python(values)


async def update_heartbeat_preferences(
    db: AsyncSession,
    actor_id: UUID,
    data: HeartbeatSettingsUpdate,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> User:
    values = normalize_heartbeat_patch(data)
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    if not values:
        return actor
    if expected is not None:
        if set(expected) != set(values):
            raise ValueError("Expected state must cover exactly the changed heartbeat fields")
        before = heartbeat_preference_values(actor, values)
        if json.dumps(before, sort_keys=True) != json.dumps(dict(expected), sort_keys=True):
            raise ResourceConflictError("preferences", detail={"error_code": "STALE_STATE"})
    raw = _VALUES.validate_python({name: getattr(actor, name) for name in values})
    if json.dumps(raw, sort_keys=True) == json.dumps(values, sort_keys=True):
        if receipt is not None:
            receipt.committed = True
            receipt.no_op = True
        return actor
    for name, value in values.items():
        setattr(actor, name, value)
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    await db.refresh(actor)
    return actor


assert_heartbeat_preference_coverage()
