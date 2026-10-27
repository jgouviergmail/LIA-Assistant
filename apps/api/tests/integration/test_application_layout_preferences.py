"""Reversible layouts use the real effect ledger and preserve concurrent UI edits."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.catalogue_registration import LAYOUT_UPDATE_MANIFEST
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.effects.runtime import reset_policy_cache
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.registry import get_global_registry
from src.domains.agents.tools import application_layout_tools
from src.domains.agents.tools.tool_registry import get_tool_strict, register_external_tool
from src.domains.users.models import User
from src.infrastructure.account_preferences import LayoutPreferencePatch, update_layout_preferences
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("manual_intervention", [False, True])
async def test_pinned_list_replace_preserves_a_newer_visible_ui_change(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    manual_intervention: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    if not any(
        manifest.name == LAYOUT_UPDATE_MANIFEST.name
        for manifest in get_global_registry().list_tool_manifests()
    ):
        get_global_registry().register_tool_manifest(LAYOUT_UPDATE_MANIFEST)
    register_external_tool(application_layout_tools.update_lia_layout_preferences_tool)
    tool = get_tool_strict("update_lia_layout_preferences_tool")
    reset_policy_cache()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("reversible_execution", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr(application_layout_tools, "get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    original = application_layout_tools.prepare_layout_content

    async def observed(db, actor_id, patch):
        content = await original(db, actor_id, patch)
        assert content.before == {"settings_shortcuts": ["font"]}
        if manual_intervention:
            await update_layout_preferences(
                db, actor_id, LayoutPreferencePatch(settings_shortcuts=["font-size"])
            )
        return content

    monkeypatch.setattr(application_layout_tools, "prepare_layout_content", observed)
    test_user.settings_shortcuts = ["font"]
    await async_session.commit()
    with (
        installed_runtime_context(user_id=test_user.id, execution_mode=mode, language="fr"),
        effect_scope(EffectScope(run_id=str(uuid4()), idempotency_key=str(uuid4()))),
    ):
        output = await tool.coroutine(
            patch=LayoutPreferencePatch(settings_shortcuts=["font", "theme"]),
            runtime=make_tool_runtime(
                user_id=test_user.id, store=InMemoryStore(), execution_mode=mode, language="fr"
            ),
        )
    await async_session.refresh(test_user)
    assert output.success is (not manual_intervention)
    assert not output.metadata.get("requires_confirmation")
    assert not output.registry_updates
    assert test_user.settings_shortcuts == (
        ["font-size"] if manual_intervention else ["font", "theme"]
    )
    if manual_intervention:
        assert output.error_code == "STALE_STATE"
    effects = list(
        (
            await async_session.scalars(
                select(AgentEffect).where(AgentEffect.user_id == test_user.id)
            )
        ).all()
    )
    assert len(effects) == 1 and effects[0].mutation_policy == "reversible"
