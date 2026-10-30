"""One failed user MCP operation has one retained diagnostic above DEBUG."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from structlog.testing import capture_logs

from src.domains.agents.tools.mcp_react_tools import _MCPReActWrapper
from src.infrastructure.mcp.user_pool import UserMCPClientPool
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

pytestmark = pytest.mark.unit


class _FailingClient:
    """The external transport fails once; the real pool and both wrappers unwind."""

    async def call_tool(self, tool_name: str, arguments: dict[str, object]) -> None:
        raise ExceptionGroup("synthetic transport", [RuntimeError("synthetic rejection")])


@asynccontextmanager
async def _connection() -> AsyncIterator[_FailingClient]:
    yield _FailingClient()


class _EphemeralPool:
    """Select the ephemeral connection without Redis or an external server."""

    async def call_tool(
        self,
        user_id: UUID,
        server_id: UUID,
        tool_name: str,
        arguments: dict[str, object],
        timeout_seconds: int,
        *,
        built_from: str | None = None,
        declaration: object = None,
    ) -> str:
        return await UserMCPClientPool._execute_call_ephemeral(
            "https://synthetic.example/mcp", None, tool_name, arguments, timeout_seconds
        )


async def test_a_failed_operation_has_one_retained_error_and_debug_unwinding() -> None:
    adapter = UserMCPToolAdapter.from_discovered_tool(
        server_id=uuid4(),
        user_id=uuid4(),
        server_name="Synthetic server",
        tool_name="synthetic_read",
        description="Synthetic read",
        input_schema={},
    )
    wrapper = _MCPReActWrapper(adapter)
    with (
        patch("src.infrastructure.mcp.user_pool._ephemeral_client", return_value=_connection()),
        patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=_EphemeralPool()),
        capture_logs() as logs,
    ):
        result = await wrapper._arun()

    assert result == "ERROR: synthetic rejection"
    failures = [
        entry
        for entry in logs
        if entry["event"]
        in {"mcp_ephemeral_call_failed", "user_mcp_tool_error", "mcp_react_wrapper_tool_error"}
    ]
    retained = [entry for entry in failures if entry["log_level"] != "debug"]
    assert [entry["event"] for entry in retained] == ["user_mcp_tool_error"]
    assert retained[0]["error_type"] == "RuntimeError"
    assert {entry["event"] for entry in failures} == {
        "mcp_ephemeral_call_failed",
        "user_mcp_tool_error",
        "mcp_react_wrapper_tool_error",
    }
