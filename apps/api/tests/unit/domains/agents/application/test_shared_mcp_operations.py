"""Native shared-server preferences prepare an owned desired state through the typed owner."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.users.models import User
from src.infrastructure.mcp.preferences_contract import SharedMCPPreferenceSnapshot
from src.infrastructure.mcp.preferences_gateway import (
    SharedMCPPreferencesGateway,
    configure_shared_mcp_preferences,
)

pytestmark = pytest.mark.unit


async def test_proposal_reads_current_owner_and_never_calls_the_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = import_module("src.domains.agents.application.shared_mcp_operations")
    schemas = import_module("src.domains.agents.application.shared_mcp_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    snapshot = SharedMCPPreferenceSnapshot(
        server_key="shared",
        name="Shared",
        enabled_for_user=True,
        tools_count=1,
        catalogue_digest="a" * 64,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor]
    read = AsyncMock(return_value=[snapshot])
    write = AsyncMock()
    previous = configure_shared_mcp_preferences(SharedMCPPreferencesGateway(read, write))
    try:
        content = await operations.prepare_shared_mcp_content(
            db,
            actor.id,
            schemas.SharedMCPPreferenceUpdateRequest(server_key="shared", enabled=False),
        )
    finally:
        configure_shared_mcp_preferences(previous)
    assert content.operation_id == "shared_mcp_preferences.update"
    assert content.before["shared_mcp_server"]["enabled_for_user"] is True
    assert content.after["shared_mcp_server"]["enabled_for_user"] is False
    read.assert_awaited_once_with(db, actor.id, "shared")
    write.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_summary_pages_do_not_skip_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    operations = import_module("src.domains.agents.application.shared_mcp_operations")
    schemas = import_module("src.domains.agents.application.shared_mcp_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    values = [
        SharedMCPPreferenceSnapshot(
            server_key=key,
            name=key,
            enabled_for_user=True,
            tools_count=1,
            catalogue_digest="a" * 64,
        )
        for key in ("third", "first", "second")
    ]
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, None, None, actor]
    previous = configure_shared_mcp_preferences(
        SharedMCPPreferencesGateway(AsyncMock(return_value=values), AsyncMock())
    )
    try:
        first = await operations.read_shared_mcp_preferences(
            db, actor.id, schemas.SharedMCPPreferenceRead(limit=1)
        )
        second = await operations.read_shared_mcp_preferences(
            db, actor.id, schemas.SharedMCPPreferenceRead(limit=2, after_key=first.next_cursor)
        )
    finally:
        configure_shared_mcp_preferences(previous)
    assert [v.server_key for v in first.servers] == ["first"]
    assert [v.server_key for v in second.servers] == ["second", "third"]
    assert first.total == second.total == 3
    assert second.next_cursor is None
    assert "catalogue_digest" not in first.model_dump_json() + second.model_dump_json()


def test_confirmation_shows_identity_and_choice_without_internal_digest() -> None:
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.agents.application.shared_mcp_schemas import SharedMCPPreferencePatch

    before = SharedMCPPreferenceSnapshot(
        server_key="shared",
        name="Shared service",
        enabled_for_user=True,
        tools_count=3,
        catalogue_digest="a" * 64,
    )
    content = _preference_content(
        uuid4(),
        SharedMCPPreferencePatch(
            shared_mcp_server=before.model_copy(update={"enabled_for_user": False})
        ),
        {"shared_mcp_server": before.model_dump(mode="json")},
    )
    lines = render_application_preview(
        content.model_dump(mode="json"),
        {
            "application_field_shared_mcp_server": "Shared server",
            "application_before": "Before",
            "application_after": "After",
            "application_expiry": "Expires",
            "application_unavailable": "Unavailable",
        },
        lambda value: value or "",
    )
    visible = str(lines)
    assert "Shared service" in visible and "shared" in visible
    assert "true" in visible and "false" in visible
    assert "a" * 64 not in visible


@pytest.mark.parametrize(
    "payload",
    [
        {"server_key": "shared", "enabled": "false"},
        {"server_key": "shared", "enabled": False, "actor_id": str(uuid4())},
        {"server_key": "shared", "enabled": False, "headers": {"key": "secret"}},
    ],
)
def test_the_model_cannot_supply_authority_or_server_configuration(payload: object) -> None:
    schemas = import_module("src.domains.agents.application.shared_mcp_schemas")
    with pytest.raises(ValidationError):
        schemas.SharedMCPPreferenceUpdateRequest.model_validate(payload)
