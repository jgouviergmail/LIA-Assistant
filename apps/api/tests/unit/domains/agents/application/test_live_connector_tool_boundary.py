"""Model-visible Live provider tools cannot receive credentials or write before HITL."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def test_connector_tool_schemas_only_offer_the_public_change_request() -> None:
    tools = import_module("src.domains.agents.tools.application_live_connector_tools")
    schema = tools.update_lia_live_connector_settings_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"change"}
    assert "credentials" not in str(schema) and "stored_digest" not in str(schema)
    assert "api_key" not in str(schema) and "actor_id" not in str(schema)
    assert not tools.get_lia_live_connector_settings_tool.tool_call_schema.model_fields


def test_options_tool_is_read_only_and_exposes_no_credentials_or_probe_parameters() -> None:
    tools = import_module("src.domains.agents.tools.application_live_options_tools")
    schema = tools.get_lia_live_options_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
    assert "api_key" not in str(schema) and "actor_id" not in str(schema)
    assert "probe" not in str(schema)


def test_live_management_is_consistently_registered_with_fresh_live_guards() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.feature_switches.registry import PlatformCapability

    names = {
        "get_lia_live_connector_settings_tool",
        "update_lia_live_connector_settings_tool",
        "get_lia_live_options_tool",
    }
    assert names <= set(APPLICATION_TOOL_NAMES)
    manifests = {manifest.name: manifest for manifest in APPLICATION_MANIFESTS}
    assert names <= set(manifests)
    specs = {spec.tool_name: spec for spec in APPLICATION_OPERATIONS.all()}
    assert names <= set(specs)
    assert all(specs[name].required_capabilities == (PlatformCapability.LIVE,) for name in names)
    assert manifests["update_lia_live_connector_settings_tool"].mutation_policy == "draft"
    assert manifests["get_lia_live_options_tool"].mutation_policy == "read"


async def test_connector_proposal_creates_confirmation_without_provider_or_settings_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langgraph.store.memory import InMemoryStore
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.config import settings
    from src.domains.connectors.models import ConnectorStatus, ConnectorType
    from src.domains.users.models import User
    from src.infrastructure.live_connector_preferences import (
        LiveConnectorPreferenceSnapshot,
        LiveConnectorSettingValues,
        configure_live_connector_preferences,
    )
    from tests.helpers.runtime_context import make_tool_runtime

    tools = import_module("src.domains.agents.tools.application_live_connector_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor]
    snapshot = LiveConnectorPreferenceSnapshot(
        connector_id=uuid4(),
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        provider="gemini",
        stored_digest="a" * 64,
    )
    gateway = AsyncMock()
    before_values = LiveConnectorSettingValues.model_validate(
        {
            "model": "model",
            "voice": "Kore",
            "thinking_level": None,
            "idle_timeout_seconds": 60,
            "session_max_minutes": 10,
            "session_budget_eur": None,
        },
    )
    gateway.prepare.return_value = (
        snapshot,
        before_values,
        before_values.model_copy(update={"voice": "Puck"}),
    )
    previous = configure_live_connector_preferences(gateway)

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(tools, "save_command", persist)
    try:
        result = await tools.update_lia_live_connector_settings_tool.coroutine(
            change={"provider": "gemini", "settings": {"voice": "Puck"}},
            runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
        )
    finally:
        configure_live_connector_preferences(previous)
    assert result.success and result.metadata["requires_confirmation"]
    persist.assert_awaited_once()
    gateway.write.assert_not_awaited()
    db.commit.assert_not_awaited()
