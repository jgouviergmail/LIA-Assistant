"""Native Pipeline/ReAct tools: real saved preferences, real ledger, no HITL."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.catalogue_registration import PREFERENCES_UPDATE_MANIFEST
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.effects.runtime import reset_policy_cache
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.registry import get_global_registry
from src.domains.agents.tools import application_action_tools
from src.domains.agents.tools.tool_registry import get_tool_strict, register_external_tool
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("scenario", ["theme", "font", "replay", "disabled", "inactive", "partial"])
async def test_reversible_settings_use_source_cas_and_current_authority(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    if not any(
        manifest.name == PREFERENCES_UPDATE_MANIFEST.name
        for manifest in get_global_registry().list_tool_manifests()
    ):
        get_global_registry().register_tool_manifest(PREFERENCES_UPDATE_MANIFEST)
    register_external_tool(application_action_tools.update_lia_preferences_tool)
    tool = get_tool_strict("update_lia_preferences_tool")
    reset_policy_cache()

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("reversible_execution", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_action_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    queue = asyncio.Queue()
    actor_id = test_user.id
    initial = test_user.font_size
    change = (
        {"mode": "set", "patch": {"color_theme": "Sage"}}
        if scenario == "theme"
        else {"mode": "increase_font"}
    )
    if scenario == "partial":
        from unittest.mock import AsyncMock

        target = "UTC" if test_user.timezone != "UTC" else "Europe/Paris"
        change = {"mode": "set", "patch": {"timezone": target}}
        monkeypatch.setattr(
            "src.infrastructure.scheduler.timezone_propagation.propagate_timezone",
            AsyncMock(side_effect=RuntimeError("controlled-private-error")),
        )
    scope = EffectScope(run_id=str(uuid4()), idempotency_key=str(uuid4()))
    with (
        installed_runtime_context(
            user_id=actor_id, execution_mode=mode, language="fr", side_channel_queue=queue
        ),
        effect_scope(scope),
    ):
        runtime = make_tool_runtime(
            user_id=actor_id, store=InMemoryStore(), execution_mode=mode, language="fr"
        )
        if scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "inactive":
            test_user.is_active = False
            await async_session.commit()
        result = await tool.coroutine(change=change, runtime=runtime)
        await async_session.refresh(test_user)
        if scenario == "partial":
            assert not result.success and result.error_code == "POST_COMMIT_FAILURE"
            assert result.structured_data["application_result"]["committed"] is True
            assert test_user.timezone == target
            assert "controlled-private-error" not in str(result.model_dump())
            return
        if scenario in {"disabled", "inactive"}:
            assert not result.success
            assert test_user.font_size == initial
            return
        assert result.success and not result.registry_updates
        assert not result.metadata.get("requires_confirmation")
        if scenario == "theme":
            assert test_user.color_theme == "forest"
            assert result.structured_data["setting_choices"]["color_theme"]["label"] == "Sauge"
        else:
            assert test_user.font_size == initial + 1
        effects = list(
            (
                await async_session.scalars(
                    select(AgentEffect).where(AgentEffect.user_id == actor_id)
                )
            ).all()
        )
        assert len(effects) == 1 and effects[0].mutation_policy == "reversible"
        assert not queue.empty()
        if scenario == "replay":
            again = await tool.coroutine(change=change, runtime=runtime)
            assert again["success"] if isinstance(again, dict) else again.success
            await async_session.refresh(test_user)
            assert test_user.font_size == initial + 1
            test_user.is_active = False
            await async_session.commit()
            revoked = await tool.coroutine(change=change, runtime=runtime)
            assert not revoked.success
