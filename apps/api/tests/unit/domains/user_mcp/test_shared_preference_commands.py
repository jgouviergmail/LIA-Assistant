"""A shared MCP server opt-out is account scoped and compared under a fresh lock."""

from importlib import import_module
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.client_manager import MCPClientManager
from src.infrastructure.mcp.schemas import MCPDiscoveredTool

pytestmark = pytest.mark.unit


def manager() -> MagicMock:
    instance = MagicMock(spec=MCPClientManager)
    instance.discovered_tools = {
        "shared": [
            MCPDiscoveredTool(
                server_name="shared",
                tool_name="read",
                description="Read public facts",
                input_schema={"type": "object", "properties": {}},
            )
        ]
    }
    return instance


async def test_desired_optout_preserves_other_saved_refusals_and_noop_does_not_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = import_module("src.domains.user_mcp.shared_preference_commands")
    monkeypatch.setattr(commands.client_manager, "get_mcp_client_manager", manager)
    actor = User(id=uuid4(), is_active=True, deleted_at=None, admin_mcp_disabled_servers=["other"])
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    before = commands.shared_mcp_snapshot(actor, "shared")
    receipt = PreferenceWriteReceipt()
    await commands.set_shared_mcp_enabled(
        db, actor.id, "shared", False, expected=before, receipt=receipt
    )
    assert actor.admin_mcp_disabled_servers == ["other", "shared"]
    assert receipt.committed and not receipt.no_op
    db.commit.assert_awaited_once()
    db.commit.reset_mock()
    receipt = PreferenceWriteReceipt()
    await commands.set_shared_mcp_enabled(
        db,
        actor.id,
        "shared",
        False,
        expected=commands.shared_mcp_snapshot(actor, "shared"),
        receipt=receipt,
    )
    assert receipt.committed and receipt.no_op
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("change", ["manual", "catalogue", "inactive"])
async def test_current_refusal_or_catalogue_change_invalidates_the_approved_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    commands = import_module("src.domains.user_mcp.shared_preference_commands")
    active_manager = manager()
    monkeypatch.setattr(commands.client_manager, "get_mcp_client_manager", lambda: active_manager)
    actor = User(id=uuid4(), is_active=True, deleted_at=None, admin_mcp_disabled_servers=[])
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    before = commands.shared_mcp_snapshot(actor, "shared")
    if change == "manual":
        actor.admin_mcp_disabled_servers = ["shared"]
    elif change == "catalogue":
        active_manager.discovered_tools["shared"][0].description = "Changed capability"
    else:
        actor.is_active = False
    with pytest.raises(ResourceNotFoundError if change == "inactive" else ResourceConflictError):
        await commands.set_shared_mcp_enabled(db, actor.id, "shared", False, expected=before)
    db.commit.assert_not_awaited()


def test_snapshot_has_no_endpoint_headers_credentials_or_raw_tool_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = import_module("src.domains.user_mcp.shared_preference_commands")
    active_manager = manager()
    active_manager.server_configs = {
        "shared": {"url": "https://private", "headers": {"secret": "key"}}
    }
    monkeypatch.setattr(commands.client_manager, "get_mcp_client_manager", lambda: active_manager)
    actor = User(id=uuid4(), admin_mcp_disabled_servers=[])
    serialized = commands.shared_mcp_snapshot(actor, "shared").model_dump_json()
    assert "https://private" not in serialized and '"headers"' not in serialized
    assert "input_schema" not in serialized


def test_new_shared_ui_fields_need_an_explicit_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import create_model

    commands = import_module("src.domains.user_mcp.shared_preference_commands")
    future = create_model(
        "FutureSharedUI", __base__=commands.AdminMCPServerResponse, credentials=(str | None, None)
    )
    monkeypatch.setattr(commands, "AdminMCPServerResponse", future)
    with pytest.raises(AssertionError):
        commands.assert_shared_preference_coverage()
