"""The routes that say what a server will do (spec 2026-10-30 D5) — and write nothing.

Called as functions, like the other route tests of this domain: ownership is the
service's check, a preview leaves the session untouched, and the strategy preview
spans every server of the account. One route writes: a tool's own choice (D6), bound
to the declaration the catalogue lists now, refused for a tool it does not list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError, StructuredValidationError
from src.domains.user_mcp.behavior_schemas import (
    BehaviorPreviewRequest,
    StrategyPreviewRequest,
    ToolConfirmationRequest,
)
from src.domains.user_mcp.router import (
    get_server_behavior,
    preview_confirmation_strategy,
    preview_server_behavior,
    router,
    set_tool_confirmation,
)
from src.domains.user_mcp.tool_choice_repository import UserMCPToolChoiceRepository
from src.infrastructure.mcp.catalogue_snapshot import build_snapshot, snapshot_to_jsonb
from src.infrastructure.mcp.confirmation import (
    StoredToolChoice,
    ToolChoice,
    declaration_fingerprint,
)
from tests._routes import served_routes

pytestmark = pytest.mark.unit

_TOOLS = [
    {"name": "delete_note", "input_schema": {}, "annotations": {"destructive_hint": True}},
    {"name": "read_note", "input_schema": {}, "annotations": {"read_only_hint": True}},
]


def _row(*, hitl: bool | None = None, name: str = "Notes") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=UUID(int=1),
        name=name,
        hitl_required=hitl,
        iterative_mode=False,
        react_expand_iterative=None,
        discovered_tools_cache=snapshot_to_jsonb(
            build_snapshot(
                tools=_TOOLS,
                configuration_fingerprint="cfg",
                discovered_at=datetime(2026, 10, 30, tzinfo=UTC),
                generation=1,
            )
        ),
    )


def _user(strategy: bool | None) -> Any:
    return SimpleNamespace(id=UUID(int=1), mcp_hitl_required=strategy)


@pytest.fixture(autouse=True)
def _instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mcp_hitl_required", False)


@pytest.fixture(autouse=True)
def _no_tool_choice(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """No tool has a choice of its own unless a test records one."""
    choices_for = AsyncMock(return_value={})
    monkeypatch.setattr(UserMCPToolChoiceRepository, "choices_for", choices_for)
    return choices_for


class TestOwnership:
    async def test_another_account_s_server_is_not_found(self) -> None:
        with patch(
            "src.domains.user_mcp.router.UserMCPServerService.get_with_ownership_check",
            AsyncMock(side_effect=ResourceNotFoundError("user_mcp_server", "x")),
        ):
            with pytest.raises(ResourceNotFoundError):
                await get_server_behavior(uuid4(), _user(None), MagicMock())  # type: ignore[arg-type]


class TestThePreviewWritesNothing:
    async def test_a_loosening_preview_lists_its_losses_and_touches_no_row(self) -> None:
        db = MagicMock()
        row = _row(hitl=True)
        with patch(
            "src.domains.user_mcp.router.UserMCPServerService.get_with_ownership_check",
            AsyncMock(return_value=row),
        ):
            preview = await preview_server_behavior(
                row.id,
                BehaviorPreviewRequest(hitl_required=None),
                _user(False),  # type: ignore[arg-type]
                db,
            )

        assert [loss.tool_name for loss in preview.questions_lost] == ["read_note"]
        assert row.hitl_required is True  # the stored row is untouched
        db.add.assert_not_called()
        db.commit.assert_not_called()
        db.flush.assert_not_called()

    async def test_the_stored_behavior_is_served(self) -> None:
        row = _row(hitl=None)
        with patch(
            "src.domains.user_mcp.router.UserMCPServerService.get_with_ownership_check",
            AsyncMock(return_value=row),
        ):
            behavior = await get_server_behavior(row.id, _user(True), MagicMock())  # type: ignore[arg-type]

        assert behavior.confirmation.always is True
        assert behavior.confirmation.source.value == "account"
        assert all(tool.asks for tool in behavior.tools)


class TestAToolsOwnChoice:
    async def test_it_is_recorded_against_the_listed_declaration_and_answered(
        self, _no_tool_choice: AsyncMock
    ) -> None:
        row = _row(hitl=True)
        db = MagicMock()
        db.commit = AsyncMock()
        recorded = AsyncMock()
        never = StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(_TOOLS[0]))
        _no_tool_choice.side_effect = [{}, {row.id: {"delete_note": never}}]
        with (
            patch(
                "src.domains.user_mcp.router.UserMCPServerService.get_with_ownership_check",
                AsyncMock(return_value=row),
            ),
            patch.object(UserMCPToolChoiceRepository, "set_choice", recorded),
        ):
            behavior = await set_tool_confirmation(
                row.id,
                ToolConfirmationRequest(tool_name="delete_note", choice=ToolChoice.NEVER),
                _user(None),  # type: ignore[arg-type]
                db,
            )

        recorded.assert_awaited_once_with(
            row.id, "delete_note", ToolChoice.NEVER, declaration_fingerprint(_TOOLS[0])
        )
        db.commit.assert_awaited_once()
        (tool,) = [t for t in behavior.tools if t.tool_name == "delete_note"]
        assert tool.choice is ToolChoice.NEVER and tool.asks is False

    async def test_null_returns_the_tool_to_the_levels_below(self) -> None:
        row = _row()
        db = MagicMock()
        db.commit = AsyncMock()
        cleared = AsyncMock()
        with (
            patch(
                "src.domains.user_mcp.router.UserMCPServerService.get_with_ownership_check",
                AsyncMock(return_value=row),
            ),
            patch.object(UserMCPToolChoiceRepository, "clear_choice", cleared),
        ):
            await set_tool_confirmation(
                row.id,
                ToolConfirmationRequest(tool_name="read_note", choice=None),
                _user(None),  # type: ignore[arg-type]
                db,
            )

        cleared.assert_awaited_once_with(row.id, "read_note")
        db.commit.assert_awaited_once()

    async def test_a_tool_the_catalogue_does_not_list_is_refused_and_nothing_written(
        self,
    ) -> None:
        row = _row()
        db = MagicMock()
        db.commit = AsyncMock()
        recorded = AsyncMock()
        with (
            patch(
                "src.domains.user_mcp.router.UserMCPServerService.get_with_ownership_check",
                AsyncMock(return_value=row),
            ),
            patch.object(UserMCPToolChoiceRepository, "set_choice", recorded),
            pytest.raises(StructuredValidationError),
        ):
            await set_tool_confirmation(
                row.id,
                ToolConfirmationRequest(tool_name="renamed_tool", choice=ToolChoice.NEVER),
                _user(None),  # type: ignore[arg-type]
                db,
            )

        recorded.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_another_account_s_server_is_not_found(self) -> None:
        with (
            patch(
                "src.domains.user_mcp.router.UserMCPServerService.get_with_ownership_check",
                AsyncMock(side_effect=ResourceNotFoundError("user_mcp_server", "x")),
            ),
            pytest.raises(ResourceNotFoundError),
        ):
            await set_tool_confirmation(
                uuid4(),
                ToolConfirmationRequest(tool_name="read_note", choice=ToolChoice.ALWAYS),
                _user(None),  # type: ignore[arg-type]
                MagicMock(),
            )

    def test_the_request_is_strict(self) -> None:
        with pytest.raises(ValueError):
            ToolConfirmationRequest(tool_name="read_note", choice="sometimes")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            ToolConfirmationRequest(tool_name="", choice=ToolChoice.ALWAYS)
        with pytest.raises(ValueError):
            ToolConfirmationRequest(tool_name="read_note")  # type: ignore[call-arg]


class TestTheStrategyPreview:
    async def test_it_spans_every_server_of_the_account(self) -> None:
        notes, files = _row(name="Notes"), _row(name="Files")
        with patch(
            "src.domains.user_mcp.router.UserMCPServerService.list_servers",
            AsyncMock(return_value=[notes, files]),
        ):
            preview = await preview_confirmation_strategy(
                StrategyPreviewRequest(mcp_hitl_required=False),
                _user(True),  # type: ignore[arg-type]
                MagicMock(),
            )

        assert {loss.server_name for loss in preview.questions_lost} == {"Notes", "Files"}
        assert {loss.tool_name for loss in preview.questions_lost} == {"read_note"}

    def test_its_path_is_never_read_as_a_server_id(self) -> None:
        paths = [context.path for context in served_routes(router)]
        strategy = paths.index("/mcp/servers/strategy/preview")

        assert all(not path.startswith("/mcp/servers/{server_id}") for path in paths[:strategy])
