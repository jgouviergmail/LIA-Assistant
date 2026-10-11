"""Live reflex proposals preserve provider identity and require current live availability."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.live.preference_gateway import SavedLivePreferences
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.live_preferences import configure_live_preferences

pytestmark = pytest.mark.unit


async def test_read_distinguishes_effective_defaults_from_explicitly_saved_values() -> None:
    operations = import_module("src.domains.agents.application.live_operations")
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        live_preferences={
            "interruptions": False,
            "end_of_speech": "invalid",
            "provider": "gemini",
        },
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, actor]
    result = await operations.read_live_preferences(db, actor.id)
    assert result.defaulted_fields == ["end_of_speech", "result_delivery"]
    assert result.preferences.interruptions is False
    assert result.preferences.end_of_speech == "normal"


@pytest.mark.parametrize("disabled", ["application_tools_enabled", "live_enabled"])
async def test_disabled_live_management_is_removed_from_discovery_and_refused_at_read(
    monkeypatch: pytest.MonkeyPatch,
    disabled: str,
) -> None:
    from contextlib import asynccontextmanager

    from src.core.exceptions import AuthorizationError
    from src.domains.agents.application.live_catalogue import LIVE_PREFERENCES_READ_MANIFEST

    operations = import_module("src.domains.agents.application.live_operations")
    discovery = import_module("src.domains.agents.application.discovery")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(settings, disabled, False)
    monkeypatch.setattr(discovery, "get_db_context", session)
    assert (
        await discovery.filter_application_manifests([LIVE_PREFERENCES_READ_MANIFEST], actor.id)
        == []
    )
    db.scalar.side_effect = [None, actor]
    with pytest.raises(AuthorizationError):
        await operations.read_live_preferences(db, actor.id)


@pytest.fixture(autouse=True)
def owner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    previous = configure_live_preferences(SavedLivePreferences())
    try:
        yield
    finally:
        configure_live_preferences(previous)


async def test_single_reflex_change_preserves_the_other_values_and_provider_without_writing() -> (
    None
):
    operations = import_module("src.domains.agents.application.live_operations")
    schemas = import_module("src.domains.agents.application.live_schemas")
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        live_preferences={
            "interruptions": False,
            "end_of_speech": "calm",
            "result_delivery": "when_idle",
            "provider": "gemini",
        },
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, actor]
    content = await operations.prepare_live_preference_content(
        db, actor.id, schemas.LivePreferenceRequest(interruptions=True)
    )
    values = content.intent["live_reflexes"]["values"]
    assert values == {
        "interruptions": True,
        "end_of_speech": "calm",
        "result_delivery": "when_idle",
    }
    assert content.intent["live_reflexes"]["provider"] == "gemini"
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"interruptions": "false"},
        {"interruptions": None},
        {"provider": "openai"},
        {"result_delivery": "unknown"},
    ],
)
def test_the_model_cannot_supply_coerced_values_provider_choice_or_empty_changes(
    payload: object,
) -> None:
    schemas = import_module("src.domains.agents.application.live_schemas")
    with pytest.raises(ValidationError):
        schemas.LivePreferenceRequest.model_validate(payload)


async def test_live_preview_and_editor_show_reflexes_without_the_private_digest_or_provider() -> (
    None
):
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.prompts import build_application_edit_prompt

    operations = import_module("src.domains.agents.application.live_operations")
    schemas = import_module("src.domains.agents.application.live_schemas")
    actor = User(
        id=uuid4(), is_active=True, deleted_at=None, live_preferences={"provider": "gemini"}
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, actor]
    content = await operations.prepare_live_preference_content(
        db, actor.id, schemas.LivePreferenceRequest(end_of_speech="calm")
    )
    digest = content.intent["live_reflexes"]["stored_digest"]
    preview = str(
        render_application_preview(
            content.model_dump(mode="json"),
            {
                "application_field_live_reflexes": "Live preferences",
                "application_live_preferences": "Applies to the next session",
                "application_before": "Before",
                "application_after": "After",
                "application_expiry": "Expires",
                "application_unavailable": "Unavailable",
            },
            lambda value: value or "",
        )
    )
    assert "calm" in preview and "normal" in preview and "next session" in preview
    assert digest not in preview and "gemini" not in preview
    prompt = str(build_application_edit_prompt(content.model_dump(mode="json"), "Choisis normal"))
    assert "interruptions" in prompt and "calm" in prompt
    assert digest not in prompt and "stored_digest" not in prompt and "gemini" not in prompt


async def test_execution_routes_live_values_to_the_shared_owner() -> None:
    from src.domains.agents.application.preference_dispatch import execute_preference_patch
    from src.domains.live.preference_commands import live_preference_snapshot

    actor = User(
        id=uuid4(), is_active=True, deleted_at=None, live_preferences={"provider": "gemini"}
    )
    snapshot = live_preference_snapshot(actor)
    desired = snapshot.model_copy(
        update={"values": snapshot.values.model_copy(update={"end_of_speech": "calm"})}
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]
    receipt = PreferenceWriteReceipt()
    await execute_preference_patch(
        db,
        actor.id,
        "live_preferences.update",
        {"live_reflexes": desired.model_dump(mode="json")},
        {"live_reflexes": snapshot.model_dump(mode="json")},
        receipt,
    )
    assert receipt.committed and actor.live_preferences["end_of_speech"] == "calm"
    assert actor.live_preferences["provider"] == "gemini"


def test_new_live_ui_fields_require_a_deliberate_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import create_model

    owner = import_module("src.domains.live.preference_gateway")
    owner.assert_live_preference_coverage()
    future = create_model(
        "FutureLivePreferences", __base__=owner.LivePreferences, new_setting=(bool, False)
    )
    monkeypatch.setattr(owner, "LivePreferences", future)
    with pytest.raises(AssertionError, match="projection review"):
        owner.assert_live_preference_coverage()
