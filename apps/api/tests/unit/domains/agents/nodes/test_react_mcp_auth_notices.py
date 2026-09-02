"""The ReAct context announces MCP servers awaiting re-authentication.

2026-09-02 incident closure: a server marked ``auth_required`` is filtered out
of tool registration (``get_enabled_active_for_user``), so on every LATER turn
the model cannot distinguish "this capability does not exist" from "this
capability is one reconnection away" — and it asserted the former to the user.
This block is the only channel telling the model (and through it, the user)
that the remedy is a reconnection in Settings, not a missing feature.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.nodes import react_context


def _patch_db_with_servers(servers: list) -> tuple:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_ctx():
        yield MagicMock()

    repo = MagicMock()
    repo.get_auth_required_for_user = AsyncMock(return_value=servers)
    return (
        patch("src.infrastructure.database.session.get_db_context", fake_ctx),
        patch(
            "src.domains.user_mcp.repository.UserMCPServerRepository",
            return_value=repo,
        ),
    )


def _server(name: str) -> MagicMock:
    server = MagicMock()
    server.name = name
    return server


@pytest.mark.unit
class TestMcpAuthNoticesBlock:
    """build_mcp_auth_notices_block — best-effort, zero tokens when healthy."""

    async def test_names_the_dead_servers_and_the_remedy(self) -> None:
        db_patch, repo_patch = _patch_db_with_servers(
            [_server("Era banque"), _server("Entreprises")]
        )
        with (
            db_patch,
            repo_patch,
            patch.object(react_context, "runtime_user_id_str", return_value=str(uuid4())),
        ):
            block = await react_context.build_mcp_auth_notices_block()

        assert block is not None
        assert "Era banque" in block
        assert "Entreprises" in block
        assert "reconnect" in block
        assert "Settings" in block
        assert "does not exist" in block

    async def test_zero_tokens_when_everything_connected(self) -> None:
        db_patch, repo_patch = _patch_db_with_servers([])
        with (
            db_patch,
            repo_patch,
            patch.object(react_context, "runtime_user_id_str", return_value=str(uuid4())),
        ):
            assert await react_context.build_mcp_auth_notices_block() is None

    async def test_no_user_id_yields_none(self) -> None:
        with patch.object(react_context, "runtime_user_id_str", return_value=None):
            assert await react_context.build_mcp_auth_notices_block() is None

    async def test_best_effort_never_raises(self) -> None:
        """A DB failure degrades to silence, never to a broken turn."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def exploding_ctx():
            raise RuntimeError("db down")
            yield  # pragma: no cover

        with (
            patch("src.infrastructure.database.session.get_db_context", exploding_ctx),
            patch.object(react_context, "runtime_user_id_str", return_value=str(uuid4())),
        ):
            assert await react_context.build_mcp_auth_notices_block() is None

    def test_block_is_wired_into_react_setup(self) -> None:
        """A block nobody injects is a rule the model never hears (ADR-248
        invariant 3). Source-level guard on the setup node's assembly list."""
        import inspect

        from src.domains.agents.nodes import react_nodes

        source = inspect.getsource(react_nodes)
        assert "build_mcp_auth_notices_block" in source
