"""Unit tests for MCP client error handling and identity.

Covers three robustness contracts:
- ``unwrap_exception_group``: anyio TaskGroups wrap the root cause in nested
  single-child ExceptionGroups; diagnostics must surface the real error.
- Modern-only server detection: a server speaking only MCP >= 2026-07-28
  rejects the legacy ``initialize`` handshake with HTTP 400 or JSON-RPC
  ``-32022``; the user must get an actionable message, not a raw transport
  error.
- ``client_info``: LIA identifies itself to MCP servers (spec SHOULD),
  instead of the SDK default ``mcp/0.1.0``.
"""

from __future__ import annotations

from uuid import uuid4

import httpx2
import pytest
from mcp.shared.exceptions import MCPError

from src.core.config import settings
from src.core.constants import MCP_ERROR_UNSUPPORTED_PROTOCOL_VERSION
from src.infrastructure.mcp.utils import (
    MCPModernOnlyServerError,
    is_modern_only_rejection,
    unwrap_exception_group,
)


def _nested_group(root: BaseException, depth: int = 2) -> BaseException:
    """Wrap ``root`` in ``depth`` single-child ExceptionGroups (anyio style)."""
    exc: BaseException = root
    for i in range(depth):
        exc = ExceptionGroup(f"level-{i}", [exc])
    return exc


class TestUnwrapExceptionGroup:
    def test_plain_exception_is_returned_unchanged(self):
        exc = ValueError("boom")
        assert unwrap_exception_group(exc) is exc

    def test_nested_single_child_groups_unwrap_to_root(self):
        root = ValueError("root cause")
        assert unwrap_exception_group(_nested_group(root, depth=3)) is root

    def test_multi_child_group_is_not_unwrapped(self):
        group = ExceptionGroup("multi", [ValueError("a"), KeyError("b")])
        assert unwrap_exception_group(group) is group


class TestModernOnlyRejectionDetection:
    def _http_error(self, status: int) -> httpx2.HTTPStatusError:
        request = httpx2.Request("POST", "https://mcp.example.com/mcp")
        response = httpx2.Response(status, request=request)
        return httpx2.HTTPStatusError("err", request=request, response=response)

    def test_http_400_on_handshake_is_modern_only(self):
        assert is_modern_only_rejection(self._http_error(400))

    def test_http_401_is_not_modern_only(self):
        assert not is_modern_only_rejection(self._http_error(401))

    def test_jsonrpc_32022_is_modern_only(self):
        err = MCPError(
            code=MCP_ERROR_UNSUPPORTED_PROTOCOL_VERSION,
            message="Unsupported protocol version",
        )
        assert is_modern_only_rejection(err)

    def test_other_mcp_error_is_not_modern_only(self):
        err = MCPError(code=-32601, message="Method not found")
        assert not is_modern_only_rejection(err)

    def test_plain_runtime_error_is_not_modern_only(self):
        assert not is_modern_only_rejection(RuntimeError("boom"))


class _FailingClient:
    """Fake SDK v2 Client raising on entry (connection failure)."""

    exc: BaseException = RuntimeError("unset")

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self):
        raise type(self).exc

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class TestUserPoolErrorSurfacing:
    """The ephemeral call path surfaces the root cause, and a modern-only
    server produces an actionable error."""

    def _pool_with_entry(self):
        from src.infrastructure.mcp.user_pool import PoolEntry, UserMCPClientPool

        pool = UserMCPClientPool()
        user_id, server_id = uuid4(), uuid4()
        pool._entries[(user_id, server_id)] = PoolEntry(
            user_id=user_id,
            server_id=server_id,
            last_used=0.0,
            url="https://mcp.example.com/mcp",
        )
        return pool, user_id, server_id

    @pytest.mark.asyncio
    async def test_modern_only_server_yields_actionable_error(self, monkeypatch):
        from src.infrastructure.mcp import user_pool as module

        request = httpx2.Request("POST", "https://mcp.example.com/mcp")
        response = httpx2.Response(400, request=request)
        http_400 = httpx2.HTTPStatusError("400", request=request, response=response)

        _FailingClient.exc = _nested_group(http_400)
        monkeypatch.setattr(module, "Client", _FailingClient)
        pool, user_id, server_id = self._pool_with_entry()

        with pytest.raises(MCPModernOnlyServerError, match="2026-07-28"):
            await pool.call_tool(user_id, server_id, "any_tool", {})

    @pytest.mark.asyncio
    async def test_deeply_nested_root_cause_is_raised(self, monkeypatch):
        """A doubly-nested ExceptionGroup surfaces its root, never
        'unhandled errors in a TaskGroup'."""
        from src.infrastructure.mcp import user_pool as module

        _FailingClient.exc = _nested_group(ValueError("real root cause"), depth=2)
        monkeypatch.setattr(module, "Client", _FailingClient)
        pool, user_id, server_id = self._pool_with_entry()

        with pytest.raises(ValueError, match="real root cause"):
            await pool.call_tool(user_id, server_id, "any_tool", {})

    @pytest.mark.asyncio
    async def test_discovery_surfaces_modern_only_server(self, monkeypatch):
        """`get_or_connect` (test-connection path) gets the same treatment —
        this is the error a user reads in the settings screen."""
        from src.infrastructure.mcp import user_pool as module

        _FailingClient.exc = _nested_group(
            MCPError(
                code=MCP_ERROR_UNSUPPORTED_PROTOCOL_VERSION,
                message="Unsupported protocol version",
            )
        )
        monkeypatch.setattr(module, "Client", _FailingClient)
        from src.infrastructure.mcp.user_pool import UserMCPClientPool

        pool = UserMCPClientPool()

        with pytest.raises(MCPModernOnlyServerError, match="2026-07-28"):
            await pool.get_or_connect(
                user_id=uuid4(),
                server_id=uuid4(),
                url="https://mcp.example.com/mcp",
                auth=httpx2.Auth(),
            )


class _FakeClient:
    """Minimal SDK v2 Client stand-in capturing constructor kwargs."""

    captured: list[dict] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        _FakeClient.captured.append(dict(kwargs))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def list_tools(self):
        from types import SimpleNamespace

        return SimpleNamespace(tools=[])

    async def call_tool(self, name: str, arguments: dict):
        from types import SimpleNamespace

        return SimpleNamespace(is_error=False, content=[])


class TestClientIdentity:
    """LIA identifies itself to MCP servers (clientInfo)."""

    @pytest.mark.asyncio
    async def test_user_pool_sends_lia_client_info(self, monkeypatch):
        from src.infrastructure.mcp import user_pool as module

        _FakeClient.captured = []
        monkeypatch.setattr(module, "Client", _FakeClient)

        from src.infrastructure.mcp.user_pool import UserMCPClientPool

        pool = UserMCPClientPool()
        await pool.get_or_connect(
            user_id=uuid4(),
            server_id=uuid4(),
            url="https://mcp.example.com/mcp",
            auth=httpx2.Auth(),
        )

        assert _FakeClient.captured, "Client was never constructed"
        info = _FakeClient.captured[0].get("client_info")
        assert info is not None, "client_info must be passed explicitly"
        assert info.name == "LIA"
        assert info.version == settings.app_version

    @pytest.mark.asyncio
    async def test_client_manager_sends_lia_client_info(self, monkeypatch):
        from src.infrastructure.mcp import client_manager as module

        _FakeClient.captured = []
        monkeypatch.setattr(module, "stdio_client", lambda params: None)
        monkeypatch.setattr(module, "Client", _FakeClient)

        from src.infrastructure.mcp.client_manager import MCPClientManager
        from src.infrastructure.mcp.schemas import MCPServerConfig, MCPTransportType

        manager = MCPClientManager()
        await manager._connect_server(
            "srv",
            MCPServerConfig(transport=MCPTransportType.STDIO, command="npx"),
        )

        assert _FakeClient.captured, "Client was never constructed"
        info = _FakeClient.captured[0].get("client_info")
        assert info is not None, "client_info must be passed explicitly"
        assert info.name == "LIA"
        assert info.version == settings.app_version
