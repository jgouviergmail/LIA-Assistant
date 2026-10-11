"""Native provider settings must carry bounded strict values and no credentials."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "change",
    [
        {"idle_timeout_seconds": True},
        {"session_max_minutes": "10"},
        {"session_budget_eur": True},
        {"session_budget_eur": float("nan")},
        {"api_key": "secret"},
        {},
        {"voice": None},
    ],
)
def test_provider_settings_delta_refuses_coercion_secret_empty_and_invalid_values(
    change: dict[str, object],
) -> None:
    module = import_module("src.domains.agents.application.live_connector_schemas")
    with pytest.raises(ValidationError):
        module.LiveConnectorChangeRequest.model_validate({"provider": "gemini", "settings": change})


def test_budget_can_be_explicitly_cleared_without_clearing_omitted_settings() -> None:
    module = import_module("src.domains.agents.application.live_connector_schemas")
    request = module.LiveConnectorChangeRequest.model_validate(
        {
            "provider": "gemini",
            "settings": {"session_budget_eur": None},
        }
    )
    assert request.settings.model_dump(exclude_unset=True) == {"session_budget_eur": None}


@pytest.mark.parametrize(
    "value,valid", [(0, True), (5, True), (3600, True), (4, False), (3601, False), (None, False)]
)
def test_duration_schema_offers_exactly_the_source_bounds(value: object, valid: bool) -> None:
    from jsonschema import Draft202012Validator

    module = import_module("src.domains.agents.application.live_connector_schemas")
    schema = module.LiveConnectorSettingsDelta.model_json_schema()
    assert Draft202012Validator(schema).is_valid({"idle_timeout_seconds": value}) is valid


async def test_connector_proposal_merges_requested_values_without_writing_or_probing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.config import settings
    from src.domains.connectors.models import ConnectorStatus, ConnectorType
    from src.domains.users.models import User
    from src.infrastructure.live_connector_preferences import (
        LiveConnectorPreferenceSnapshot,
        configure_live_connector_preferences,
    )

    module = import_module("src.domains.agents.application.live_connector_operations")
    schemas = import_module("src.domains.agents.application.live_connector_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    snapshot = LiveConnectorPreferenceSnapshot(
        connector_id=uuid4(),
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        provider="gemini",
        stored_digest="a" * 64,
    )
    saved = {
        "model": "model",
        "voice": "Kore",
        "thinking_level": None,
        "idle_timeout_seconds": 60,
        "session_max_minutes": 10,
        "session_budget_eur": 2.5,
    }
    gateway = AsyncMock()
    from src.infrastructure.live_connector_preferences import LiveConnectorSettingValues

    gateway.prepare.return_value = (
        snapshot,
        LiveConnectorSettingValues.model_validate(saved),
        LiveConnectorSettingValues.model_validate({**saved, "voice": "Puck"}),
    )
    previous = configure_live_connector_preferences(gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor]
    try:
        content = await module.prepare_live_connector_content(
            db,
            actor.id,
            schemas.LiveConnectorChangeRequest(provider="gemini", settings={"voice": "Puck"}),
        )
    finally:
        configure_live_connector_preferences(previous)
    assert content.intent["live_connector_settings"]["settings"] == {**saved, "voice": "Puck"}
    assert content.before["live_connector_settings"]["settings"] == saved
    from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
    from src.domains.agents.application.draft_rendering import render_application_preview

    preview = str(
        render_application_preview(
            content.model_dump(mode="json"), DRAFT_PREVIEW_LABELS["fr"], lambda value: value or ""
        )
    )
    assert "Puck" in preview and "Kore" in preview
    assert "stored_digest" not in preview and snapshot.stored_digest not in preview
    gateway.write.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_new_source_live_settings_require_explicit_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import create_model

    owner = import_module("src.domains.live.connector_preference_gateway")
    owner.assert_live_connector_projection_coverage()
    future = create_model(
        "FutureLiveSettings", __base__=owner.LiveConnectorSettings, extra_setting=(bool, False)
    )
    monkeypatch.setattr(owner, "LiveConnectorSettings", future)
    with pytest.raises(AssertionError, match="projection review"):
        owner.assert_live_connector_projection_coverage()


@pytest.mark.parametrize("payload", [{}, {"voice": None}, {"model": None}, {"api_key": "secret"}])
def test_model_schema_refuses_requests_the_validator_refuses(payload: dict[str, object]) -> None:
    from jsonschema import Draft202012Validator

    module = import_module("src.domains.agents.application.live_connector_schemas")
    assert not Draft202012Validator(module.LiveConnectorSettingsDelta.model_json_schema()).is_valid(
        payload
    )


@pytest.mark.parametrize(
    "budget,valid",
    [(None, True), (2.5, True), (100, True), (0, False), (101, False), (True, False)],
)
def test_budget_schema_preserves_the_source_ceiling_and_explicit_clear(
    budget: object, valid: bool
) -> None:
    from jsonschema import Draft202012Validator

    module = import_module("src.domains.agents.application.live_connector_schemas")
    assert (
        Draft202012Validator(module.LiveConnectorSettingsDelta.model_json_schema()).is_valid(
            {"session_budget_eur": budget}
        )
        is valid
    )


@pytest.mark.parametrize("editor_name", ["_rebuild_live_connector", "_rebuild_live_preferences"])
async def test_live_editor_refuses_foreign_or_absent_runtime_before_any_read(
    editor_name: str,
) -> None:
    from datetime import UTC, datetime, timedelta

    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from tests.helpers.runtime_context import installed_runtime_context

    owner = import_module("src.domains.agents.application.draft_editing")
    content = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=uuid4(),
        operation_id="live_preferences.update",
        schema_fingerprint="a" * 64,
        expected_digest="b" * 64,
        intent={},
        before={},
        after={},
        title="Live",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    with (
        installed_runtime_context(user_id=uuid4()),
        pytest.raises(CommandRejected, match="FORBIDDEN"),
    ):
        await getattr(owner, editor_name)(content, {"intent": {}})
