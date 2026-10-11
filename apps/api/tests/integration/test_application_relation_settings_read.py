"""Native relationship settings expose current source controls without provider/LLM work."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.relation_settings_read import read_relation_settings
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["saved", "default", "legacy", "personal_off", "native_off"])
async def test_relationship_settings_follow_owned_source_controls(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    scope = {
        "sections": ["emails"],
        "directions": ["received"],
        "roles": ["organizer"],
        "max_items": 3,
    }
    stored = None if scenario == "default" else {"max_items": -1} if scenario == "legacy" else scope
    await async_session.execute(
        update(User)
        .where(User.id == owner)
        .values(relation_overview_scope=stored, relation_debrief_enabled=scenario != "personal_off")
    )
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.relations.providers.service.RelationContextService.build",
        AsyncMock(side_effect=AssertionError("Settings must not fetch provider data")),
    )
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.RelationDebriefService.build",
        AsyncMock(side_effect=AssertionError("Settings must not generate a debrief")),
    )
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        with pytest.raises(AuthorizationError):
            await read_relation_settings(async_session, owner)
        return
    observed = await read_relation_settings(async_session, owner)
    assert observed.overview_scope == RelationOverviewScope.from_stored(stored)
    assert observed.debrief_enabled == (scenario != "personal_off")
    assert set(observed.model_dump()) == {
        "overview_scope",
        "debrief_enabled",
        "debrief_platform_enabled",
        "observed_at",
    }


@pytest.mark.parametrize(
    "scenario", ["platform_off", "late_native_off", "late_actor_off", "oversized"]
)
async def test_actual_relation_tool_refuses_withdrawn_access_and_bounds_context(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    monkeypatch.setattr(settings, "relation_debrief_enabled", True)
    if scenario == "platform_off":
        async_session.add(
            SystemSetting(key=SystemSettingKey.CAPABILITY_RELATION_DEBRIEF_ENABLED, value="false")
        )
    if scenario == "oversized":
        test_user.relation_overview_scope = {"sections": ["emails"] * 100}
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    if scenario.startswith("late_"):
        from src.domains.agents.application import relation_settings_read

        original = relation_settings_read._debrief_available

        async def withdraw(db):
            available = await original(db)
            if scenario == "late_native_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                await db.execute(update(User).where(User.id == owner).values(is_active=False))
                await db.commit()
            return available

        monkeypatch.setattr(relation_settings_read, "_debrief_available", withdraw)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_relation_tools.get_lia_relation_settings_tool.coroutine(
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore())
        )
    if scenario == "platform_off":
        assert result.success and result.structured_data["debrief_platform_enabled"] is False
    else:
        assert not result.success
        assert (
            result.error_code
            == {
                "late_native_off": "CAPABILITY_DISABLED",
                "late_actor_off": "FORBIDDEN",
                "oversized": "INVALID_RESPONSE_FORMAT",
            }[scenario]
        )
        assert not result.structured_data
