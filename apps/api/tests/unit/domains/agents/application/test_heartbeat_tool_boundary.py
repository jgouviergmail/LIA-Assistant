"""Both orchestration modes offer a private, exact heartbeat confirmation boundary."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_confirmation_displays_refusals_and_overnight_hours_in_every_locale(language: str) -> None:
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.heartbeat_schemas import HeartbeatPreferencePatch
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.agents.drafts.card_spec import Note, Row

    patch = HeartbeatPreferencePatch(
        heartbeat_disabled_sources=["emails"],
        heartbeat_notify_start_hour=22,
        heartbeat_notify_end_hour=6,
    )
    draft = _preference_content(
        uuid4(),
        patch,
        {
            "heartbeat_disabled_sources": ["calendar"],
            "heartbeat_notify_start_hour": 8,
            "heartbeat_notify_end_hour": 20,
        },
    )
    lines = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    assert not any(isinstance(line, Note) for line in lines)
    rows = [line for line in lines if isinstance(line, Row)]
    assert len(rows) == 4
    text = str(rows)
    assert all(value in text for value in ("calendar", "emails", "22", "6"))


def test_pipeline_and_react_offer_the_same_closed_heartbeat_patch() -> None:
    catalogue = import_module("src.domains.agents.application.heartbeat_catalogue")
    tools = import_module("src.domains.agents.tools.application_heartbeat_tools")
    manifest = catalogue.HEARTBEAT_UPDATE_MANIFEST
    schema = manifest.parameters[0].schema
    assert schema is not None
    validator = Draft202012Validator(schema)
    assert validator.is_valid({"heartbeat_enabled": False})
    for value in (
        {},
        {"heartbeat_enabled": None},
        {"user_id": str(uuid4())},
        {"heartbeat_notify_start_hour": 24},
    ):
        assert not validator.is_valid(value)
    assert (
        "runtime" not in tools.update_lia_heartbeat_preferences_tool.tool_call_schema.model_fields
    )
    assert APPLICATION_OPERATIONS.get("heartbeat_preferences.update").tool_name == manifest.name
    assert manifest.mutation_policy == "draft"


async def test_raw_pipeline_change_only_persists_a_confirmable_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_heartbeat_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    # The UI still permits saving preferences while the delivery platform is paused.
    monkeypatch.setattr(settings, "heartbeat_enabled", False)
    actor = User(id=uuid4(), is_active=True, deleted_at=None, heartbeat_enabled=True)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    from src.domains.agents.tools.output import UnifiedToolOutput

    persist.return_value = UnifiedToolOutput.data_success(message="Saved", structured_data={})
    monkeypatch.setattr(
        "src.domains.agents.application.reversible_execution.execute_reversible_change", persist
    )
    result = await tools.update_lia_heartbeat_preferences_tool.coroutine(
        patch={"heartbeat_enabled": False},
        runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
    )
    assert result.success
    content = persist.await_args.args[0]
    assert content.actor_id == actor.id
    assert content.before == {"heartbeat_enabled": True}
    assert content.after == {"heartbeat_enabled": False}
    assert actor.heartbeat_enabled is True
    assert not result.registry_updates


async def test_operator_refusal_blocks_even_a_previously_bound_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_heartbeat_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = "false"

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(
        "src.domains.agents.application.native_tool_preparation.save_command", persist
    )
    result = await tools.update_lia_heartbeat_preferences_tool.coroutine(
        patch={"heartbeat_enabled": False},
        runtime=make_tool_runtime(user_id=uuid4(), store=InMemoryStore()),
    )
    assert not result.success
    assert result.error_code == "CAPABILITY_DISABLED"
    persist.assert_not_awaited()
    assert db.scalar.await_count == 1
