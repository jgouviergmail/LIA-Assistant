"""The server's card says when a tool's « never » is suspended (spec 2026-10-30 D6).

A « never » is bound to the declaration it was chosen against; when the server changes
that declaration the choice stops applying, and the synthesis AND the card say so until
the person chooses again. The list reads every server's choices in one query and each
row carries its count; a single row's answer counts the same way.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.user_mcp.projection import owned_server_response, server_to_response
from src.domains.user_mcp.router import list_servers
from src.infrastructure.mcp.catalogue_snapshot import build_snapshot, snapshot_to_jsonb
from src.infrastructure.mcp.confirmation import (
    StoredToolChoice,
    ToolChoice,
    declaration_fingerprint,
)

pytestmark = pytest.mark.unit

_DELETE: dict[str, Any] = {
    "name": "delete_note",
    "input_schema": {},
    "annotations": {"destructive_hint": True},
}
_STALE = StoredToolChoice(ToolChoice.NEVER, "a declaration the server has since changed")


def _row(name: str = "Notes") -> Any:
    now = datetime(2026, 10, 30, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(),
        user_id=UUID(int=1),
        name=name,
        url="https://notes.example/mcp",
        auth_type="none",
        status="active",
        is_enabled=True,
        plugin_id=None,
        domain_description=None,
        timeout_seconds=30,
        hitl_required=None,
        iterative_mode=False,
        react_expand_iterative=None,
        last_connected_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        discovered_tools_cache=snapshot_to_jsonb(
            build_snapshot(
                tools=[_DELETE],
                configuration_fingerprint="cfg",
                discovered_at=now,
                generation=1,
            )
        ),
    )


def _service() -> MagicMock:
    service = MagicMock()
    service.build_response_metadata.return_value = {
        "header_name": None,
        "has_credentials": False,
        "has_oauth_credentials": False,
        "oauth_scopes": None,
    }
    return service


def test_a_row_counts_its_suspended_choices() -> None:
    row = _row()
    current = StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(_DELETE))

    stale = server_to_response(row, _service(), tool_choices={"delete_note": _STALE})
    applied = server_to_response(row, _service(), tool_choices={"delete_note": current})
    plain = server_to_response(row, _service())

    assert stale.suspended_tool_choices == 1
    assert applied.suspended_tool_choices == 0
    assert plain.suspended_tool_choices == 0


async def test_the_list_reads_every_server_s_choices_once() -> None:
    notes, files = _row("Notes"), _row("Files")
    service = _service()
    service.list_servers = AsyncMock(return_value=[notes, files])
    service.repository.tool_choices = AsyncMock(return_value={notes.id: {"delete_note": _STALE}})
    user = SimpleNamespace(id=UUID(int=1), mcp_hitl_required=None)
    with (
        patch("src.domains.user_mcp.router.UserMCPServerService", return_value=service),
        patch("src.domains.user_mcp.router.capability_origins", AsyncMock(return_value={})),
        patch("src.domains.user_mcp.router.capability_shares", AsyncMock(return_value={})),
    ):
        listed = await list_servers(user, MagicMock())  # type: ignore[arg-type]

    service.repository.tool_choices.assert_awaited_once_with([notes.id, files.id])
    assert [s.suspended_tool_choices for s in listed.servers] == [1, 0]


async def test_a_single_row_answer_counts_the_same_way() -> None:
    row = _row()
    service = _service()
    service.repository.tool_choices = AsyncMock(return_value={row.id: {"delete_note": _STALE}})
    with (
        patch("src.domains.user_mcp.projection.capability_origins", AsyncMock(return_value={})),
        patch("src.domains.user_mcp.projection.capability_shares", AsyncMock(return_value={})),
    ):
        response = await owned_server_response(MagicMock(), row, service)  # type: ignore[arg-type]

    assert response.suspended_tool_choices == 1


async def test_the_assistant_reads_the_same_count() -> None:
    """A count shown is exact or absent: the assistant's read surface counts the same way."""
    from src.domains.user_mcp.management_projection import read_personal_mcp_metadata

    row = _row()
    service = _service()
    service.repository.get_page_for_user = AsyncMock(return_value=([row], 1))
    service.repository.tool_choices = AsyncMock(return_value={row.id: {"delete_note": _STALE}})
    with patch(
        "src.domains.user_mcp.management_projection.UserMCPServerService", return_value=service
    ):
        items, total = await read_personal_mcp_metadata(
            MagicMock(),
            UUID(int=1),
            server_id=None,
            offset=0,
            limit=10,
            tools_offset=0,
            tools_limit=10,
        )

    assert total == 1
    assert items[0].suspended_tool_choices == 1
    service.repository.tool_choices.assert_awaited_once_with([row.id])


class TestEachToolSaysItsOwnChoice:
    """The assistant describes the choices it reads (spec 2026-10-30 D7): each listed tool
    carries the person's choice that applies, and a suspended « never » says so."""

    def test_the_page_s_list_and_the_assistant_read_the_same_choice(self) -> None:
        current = StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(_DELETE))

        applied = server_to_response(_row(), _service(), tool_choices={"delete_note": current})
        stale = server_to_response(_row(), _service(), tool_choices={"delete_note": _STALE})
        plain = server_to_response(_row(), _service())

        assert [(t.choice, t.choice_suspended) for t in applied.tools] == [
            (ToolChoice.NEVER, False)
        ]
        assert [(t.choice, t.choice_suspended) for t in stale.tools] == [(None, True)]
        assert [(t.choice, t.choice_suspended) for t in plain.tools] == [(None, False)]

    async def test_the_assistant_s_read_surface_carries_it(self) -> None:
        from src.domains.user_mcp.management_projection import read_personal_mcp_metadata

        row = _row()
        service = _service()
        service.repository.get_page_for_user = AsyncMock(return_value=([row], 1))
        always = StoredToolChoice(ToolChoice.ALWAYS, "any")
        service.repository.tool_choices = AsyncMock(return_value={row.id: {"delete_note": always}})
        with patch(
            "src.domains.user_mcp.management_projection.UserMCPServerService", return_value=service
        ):
            items, _ = await read_personal_mcp_metadata(
                MagicMock(),
                UUID(int=1),
                server_id=None,
                offset=0,
                limit=10,
                tools_offset=0,
                tools_limit=10,
            )

        (tool,) = items[0].tools
        assert (tool.choice, tool.choice_suspended) == (ToolChoice.ALWAYS, False)
