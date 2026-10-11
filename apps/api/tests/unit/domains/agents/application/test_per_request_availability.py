"""Disabled application operations disappear before any model selects a tool."""

from contextlib import asynccontextmanager
from dataclasses import replace
from importlib import import_module
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.application.catalogue_registration import PREFERENCES_READ_MANIFEST
from src.domains.users.models import User

pytestmark = pytest.mark.unit


async def test_a_domain_condition_hides_only_its_tools_without_duplicate_capability_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings
    from src.domains.agents.application import discovery
    from src.domains.agents.application.channel_catalogue import CHANNELS_READ_MANIFEST

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "channels_enabled", True)
    actor = User(id=uuid4(), is_active=True, is_superuser=False, deleted_at=None)
    db = AsyncMock()
    db.scalar.side_effect = [None, actor, "false"]

    @asynccontextmanager
    async def database():
        yield db

    monkeypatch.setattr(discovery, "get_db_context", database)
    selected = await discovery.filter_application_manifests(
        [PREFERENCES_READ_MANIFEST, CHANNELS_READ_MANIFEST], actor.id
    )
    assert selected == [PREFERENCES_READ_MANIFEST]
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("operator_enabled", [True, False])
async def test_request_filter_preserves_other_tools_and_removes_disabled_application_tools(
    operator_enabled: bool,
) -> None:
    try:
        module = import_module("src.domains.agents.application.discovery")
    except ModuleNotFoundError:
        pytest.fail("The application request-manifest filter is missing")
    user = User(id=uuid4(), is_active=True, is_superuser=False, deleted_at=None)
    db = AsyncMock()
    db.scalar.side_effect = ["true" if operator_enabled else "false", user]

    @asynccontextmanager
    async def database():
        yield db

    unrelated = replace(PREFERENCES_READ_MANIFEST, name="unrelated_read_tool")
    offered = [unrelated, PREFERENCES_READ_MANIFEST]
    with (
        patch.object(module, "get_db_context", database),
        patch(
            "src.domains.agents.application.availability.settings.application_tools_enabled", True
        ),
    ):
        selected = await module.filter_application_manifests(offered, user.id)

    assert selected == offered if operator_enabled else selected == [unrelated]
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("offered", [False, True])
def test_analyzer_only_offers_the_application_domain_when_authorized_tools_exist(
    offered: bool,
) -> None:
    from src.core.context import request_tool_manifests_ctx
    from src.domains.agents.services.analysis.domain_availability import build_available_domains

    token = request_tool_manifests_ctx.set([PREFERENCES_READ_MANIFEST] if offered else [])
    try:
        domains = {item["name"] for item in build_available_domains()}
    finally:
        request_tool_manifests_ctx.reset(token)
    assert ("setting" in domains) is offered
