"""Heartbeat proposals publish real bounds and canonical choices before approval."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.heartbeat.preference_commands import HEARTBEAT_PREFERENCE_FIELDS
from src.domains.moments.models import MomentKind
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"heartbeat_enabled": None},
        {"heartbeat_enabled": "true"},
        {"heartbeat_notify_start_hour": True},
        {"heartbeat_notify_end_hour": 24},
        {"heartbeat_notify_start_hour": -1},
        {"heartbeat_disabled_sources": ["forged"]},
        {"is_superuser": True},
    ],
)
def test_native_patch_refuses_empty_null_coerced_or_unknown_intent(payload: object) -> None:
    schemas = import_module("src.domains.agents.application.heartbeat_schemas")
    with pytest.raises(ValidationError):
        schemas.HeartbeatPreferencePatch.model_validate(payload)


def test_canonical_lists_and_overnight_hours_are_the_exact_preview_intent() -> None:
    schemas = import_module("src.domains.agents.application.heartbeat_schemas")
    kind = MomentKind.EVENT_FOLLOWUP.value
    patch = schemas.HeartbeatPreferencePatch.model_validate(
        {
            "heartbeat_notify_start_hour": 22,
            "heartbeat_notify_end_hour": 6,
            "heartbeat_disabled_sources": ["emails", "calendar", "emails"],
            "moment_kinds_disabled": ["retired_kind", kind, kind],
        }
    )
    assert patch.model_dump(mode="json", exclude_unset=True) == {
        "heartbeat_notify_start_hour": 22,
        "heartbeat_notify_end_hour": 6,
        "heartbeat_disabled_sources": ["calendar", "emails"],
        "moment_kinds_disabled": [kind],
    }


def test_published_schema_covers_the_reviewed_http_fields_and_real_limits() -> None:
    schemas = import_module("src.domains.agents.application.heartbeat_schemas")
    schema = schemas.HeartbeatPreferencePatch.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["minProperties"] == 1
    assert set(schema["properties"]) == HEARTBEAT_PREFERENCE_FIELDS
    assert schema["properties"]["heartbeat_enabled"]["type"] == "boolean"
    for field in ("heartbeat_notify_start_hour", "heartbeat_notify_end_hour"):
        assert schema["properties"][field]["minimum"] == 0
        assert schema["properties"][field]["maximum"] == 23
        assert schema["properties"][field]["type"] == "integer"


@pytest.mark.parametrize(
    "fields", [[], ["heartbeat_enabled", "heartbeat_enabled"], ["is_superuser"]]
)
def test_read_selectors_cannot_be_empty_duplicate_or_read_other_columns(fields: object) -> None:
    schemas = import_module("src.domains.agents.application.heartbeat_schemas")
    with pytest.raises(ValidationError):
        schemas.HeartbeatPreferenceRead.model_validate({"fields": fields})


@pytest.mark.parametrize("prepare", [False, True])
async def test_current_saved_values_are_read_without_writing_before_confirmation(
    monkeypatch: pytest.MonkeyPatch, prepare: bool
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        heartbeat_enabled=True,
        heartbeat_notify_start_hour=8,
        heartbeat_notify_end_hour=22,
        heartbeat_disabled_sources=None,
        moment_kinds_disabled=None,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]
    operations = import_module("src.domains.agents.application.heartbeat_operations")
    schemas = import_module("src.domains.agents.application.heartbeat_schemas")
    monkeypatch.setattr(
        operations, "compute_available_sources", AsyncMock(return_value=[]), raising=False
    )
    db.scalar.side_effect = [None, actor, None]
    if prepare:
        result = await operations.prepare_heartbeat_content(
            db, actor.id, schemas.HeartbeatPreferencePatch(heartbeat_enabled=False)
        )
        assert result.operation_id == "heartbeat_preferences.update"
        assert result.actor_id == actor.id
        assert result.before == {"heartbeat_enabled": True}
        assert result.after == result.intent == {"heartbeat_enabled": False}
    else:
        result = await operations.read_heartbeat_preferences(
            db,
            actor.id,
            schemas.HeartbeatPreferenceRead.model_validate(
                {"fields": ["heartbeat_enabled", "heartbeat_disabled_sources"]}
            ),
        )
        assert result.values == {"heartbeat_enabled": True, "heartbeat_disabled_sources": []}
    assert actor.heartbeat_enabled is True
    db.commit.assert_not_awaited()


async def test_saved_enabled_does_not_claim_delivery_when_operator_disables_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    operations = import_module("src.domains.agents.application.heartbeat_operations")
    schemas = import_module("src.domains.agents.application.heartbeat_schemas")
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        heartbeat_enabled=True,
        heartbeat_notify_start_hour=8,
        heartbeat_notify_end_hour=22,
        heartbeat_disabled_sources=["calendar"],
        moment_kinds_disabled=None,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, "false"]
    availability = AsyncMock(return_value=["calendar", "departure", "emails"])
    monkeypatch.setattr(operations, "compute_available_sources", availability, raising=False)
    result = await operations.read_heartbeat_preferences(
        db, actor.id, schemas.HeartbeatPreferenceRead()
    )
    assert result.values["heartbeat_enabled"] is True
    assert result.platform_enabled is False
    assert result.delivery_enabled is False
    assert result.source_status.available_sources == ["calendar", "departure", "emails"]
    assert result.source_status.disabled_sources == ["calendar"]
    assert result.source_status.source_dependencies == {"departure": ["calendar"]}
    db.commit.assert_not_awaited()


async def test_a_disabled_application_capability_blocks_the_heartbeat_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings
    from src.core.exceptions import AuthorizationError

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = "false"
    operations = import_module("src.domains.agents.application.heartbeat_operations")
    schemas = import_module("src.domains.agents.application.heartbeat_schemas")
    with pytest.raises(AuthorizationError):
        await operations.read_heartbeat_preferences(db, uuid4(), schemas.HeartbeatPreferenceRead())
    assert db.scalar.await_count == 1
    db.commit.assert_not_awaited()
