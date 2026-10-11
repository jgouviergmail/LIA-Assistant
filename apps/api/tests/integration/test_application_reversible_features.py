"""Feature switches share the native gate, actual source writers and current rights."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.effects.runtime import reset_policy_cache
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.registry import get_global_registry
from src.domains.agents.tools.tool_registry import get_tool_strict, register_external_tool
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration

PORTS = [
    (
        "application_action_tools",
        "update_lia_assistant_preferences_tool",
        {"voice_mode_enabled": False},
    ),
    ("application_habit_action_tools", "update_lia_habit_settings_tool", {"habits_enabled": False}),
    (
        "application_psyche_tools",
        "update_lia_psyche_settings_tool",
        {"psyche_display_avatar": False},
    ),
    ("application_journal_tools", "update_lia_journal_settings_tool", {"journals_enabled": False}),
    (
        "application_interest_tools",
        "update_lia_interest_settings_tool",
        {"interests_enabled": False},
    ),
    (
        "application_heartbeat_tools",
        "update_lia_heartbeat_preferences_tool",
        {"heartbeat_enabled": False},
    ),
    (
        "application_interest_tools",
        "update_lia_interest_settings_tool",
        {"interests_notify_start_hour": 10, "interests_notify_end_hour": 19},
    ),
    (
        "application_interest_tools",
        "update_lia_interest_settings_tool",
        {"interests_notify_start_hour": 22, "interests_notify_end_hour": 6},
    ),
]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("module_name, name, patch", PORTS)
async def test_native_feature_preferences_are_saved_without_confirmation(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    module_name: str,
    name: str,
    patch: dict[str, bool | int],
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    for key in (
        "habits_enabled",
        "psyche_enabled",
        "journals_enabled",
        "interests_enabled",
        "heartbeat_enabled",
    ):
        if hasattr(settings, key):
            monkeypatch.setattr(settings, key, True)
    for field, value in patch.items():
        if type(value) is bool:
            setattr(test_user, field, True)
    test_user.psyche_enabled = True
    await async_session.commit()
    actor_id = test_user.id

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    module = import_module(f"src.domains.agents.tools.{module_name}")
    monkeypatch.setattr(module, "get_db_context", database)
    for source in ("reversible_execution", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{source}.get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    registry = get_global_registry()
    if not any(manifest.name == name for manifest in registry.list_tool_manifests()):
        registry.register_tool_manifest(
            next(manifest for manifest in APPLICATION_MANIFESTS if manifest.name == name)
        )
    register_external_tool(getattr(module, name))
    tool = get_tool_strict(name)
    reset_policy_cache()
    queue = asyncio.Queue()
    scope = EffectScope(run_id=str(uuid4()), idempotency_key=str(uuid4()))
    with (
        installed_runtime_context(user_id=actor_id, execution_mode=mode, side_channel_queue=queue),
        effect_scope(scope),
    ):
        runtime = make_tool_runtime(user_id=actor_id, execution_mode=mode, store=InMemoryStore())
        output = await tool.coroutine(patch=patch, runtime=runtime)
    assert output.success and not output.registry_updates
    assert not output.metadata.get("requires_confirmation")
    await async_session.refresh(test_user)
    for field, value in patch.items():
        assert getattr(test_user, field) == value
    effects = list(
        (
            await async_session.scalars(select(AgentEffect).where(AgentEffect.user_id == actor_id))
        ).all()
    )
    assert len(effects) == 1 and effects[0].mutation_policy == "reversible"
    assert not queue.empty()
