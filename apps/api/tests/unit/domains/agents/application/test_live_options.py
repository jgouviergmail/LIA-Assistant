"""Choice discovery retains provenance and refuses stale or hidden pages."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("disabled", ["application_tools_enabled", "live_enabled"])
async def test_disabled_capability_stops_discovery_before_provider_work(
    monkeypatch: pytest.MonkeyPatch, disabled: str
) -> None:
    from src.core.config import settings
    from src.core.exceptions import AuthorizationError
    from src.infrastructure.live_connector_preferences import configure_live_connector_preferences

    module = import_module("src.domains.agents.application.live_options_operations")
    schema = import_module("src.domains.agents.application.live_options_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    monkeypatch.setattr(settings, disabled, False)
    gateway = AsyncMock()
    previous = configure_live_connector_preferences(gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    try:
        with pytest.raises(AuthorizationError):
            await module.read_live_options(db, uuid4(), schema.LiveOptionsRead(section="models"))
    finally:
        configure_live_connector_preferences(previous)
    gateway.options.assert_not_awaited()


async def test_revocation_during_listing_withholds_the_returned_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings
    from src.core.exceptions import AuthorizationError
    from src.domains.users.models import User
    from src.infrastructure.live_connector_preferences import (
        LiveOptionsProjection,
        configure_live_connector_preferences,
    )

    module = import_module("src.domains.agents.application.live_options_operations")
    schema = import_module("src.domains.agents.application.live_options_schemas")
    actor = User(id=uuid4(), is_active=True, deleted_at=None, language="fr")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    gateway = AsyncMock()

    async def revoke(*args, **kwargs):
        settings.application_tools_enabled = False
        return LiveOptionsProjection(choices=[{"name": "private-agent"}], details={})

    gateway.options.side_effect = revoke
    previous = configure_live_connector_preferences(gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor]
    try:
        with pytest.raises(AuthorizationError):
            await module.read_live_options(db, actor.id, schema.LiveOptionsRead(section="models"))
    finally:
        configure_live_connector_preferences(previous)
    gateway.options.assert_awaited_once()


def test_options_pages_are_bound_to_catalogue_and_continue_only_visible_items() -> None:
    module = import_module("src.domains.agents.application.live_options_operations")
    schema = import_module("src.domains.agents.application.live_options_schemas")
    from src.infrastructure.live_connector_preferences import LiveOptionsProjection

    catalogue = LiveOptionsProjection(
        choices=[{"name": str(index), "provider": "gemini"} for index in range(60)],
        details={"section": "models", "default_model": "0", "unpriced": ["hidden"]},
    )
    first = module.page_live_options(catalogue, schema.LiveOptionsRead(section="models", limit=2))
    assert len(first["choices"]) == 2 and first["total"] == 60
    second_request = schema.LiveOptionsRead(section="models", limit=2, cursor=first["next_cursor"])
    second = module.page_live_options(catalogue, second_request)
    assert [item["name"] for item in second["choices"]] == ["2", "3"]
    catalogue.choices.reverse()
    with pytest.raises(ValueError, match="changed"):
        module.page_live_options(catalogue, second_request)


def test_discovery_never_silently_accepts_duplicate_provider_model_identities() -> None:
    module = import_module("src.domains.agents.application.live_options_operations")
    schema = import_module("src.domains.agents.application.live_options_schemas")
    from src.infrastructure.live_connector_preferences import LiveOptionsProjection

    catalogue = LiveOptionsProjection(choices=[{"name": "m", "provider": "g"}] * 2, details={})
    with pytest.raises(ValueError, match="identity"):
        module.page_live_options(catalogue, schema.LiveOptionsRead(section="models"))


def test_token_budget_advances_cursor_after_last_choice_shown() -> None:
    import json

    from src.domains.agents.tools.output import UnifiedToolOutput
    from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm

    module = import_module("src.domains.agents.application.live_options_operations")
    schema = import_module("src.domains.agents.application.live_options_schemas")
    from src.infrastructure.live_connector_preferences import LiveOptionsProjection

    choices = [{"name": str(i), "characteristic": "long " * 300} for i in range(12)]
    catalogue = LiveOptionsProjection(choices=choices, details={"provenance": "published"})
    page = module.page_live_options(
        catalogue, schema.LiveOptionsRead(section="voices", provider="gemini", limit=10)
    )
    output = UnifiedToolOutput.data_success(
        message="choices", structured_data=page, metadata={"application_live_options_cursor": True}
    )
    rendered = json.loads(extract_data_for_llm(output, budget_tokens=120))
    assert 0 < len(rendered["choices"]) < 10
    assert rendered["next_cursor"] == f'{page["catalogue_digest"]}:{len(rendered["choices"])}'
    assert page["next_cursor"].endswith(":10"), "Canonical result must remain intact"


def test_new_configuration_and_choice_fields_require_explicit_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import create_model

    owner = import_module("src.domains.live.connector_preference_gateway")
    owner.assert_live_connector_projection_coverage()
    future = create_model(
        "FutureLiveConfig", __base__=owner.LiveConfigResponse, private_runtime=(str, "private")
    )
    monkeypatch.setattr(owner, "LiveConfigResponse", future)
    with pytest.raises(AssertionError, match="projection review"):
        owner.assert_live_connector_projection_coverage()
