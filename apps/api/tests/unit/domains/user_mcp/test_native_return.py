"""The MCP authorization comes home to the shell — the half lot 3 left untested.

The connector flows had their native return pinned from the start; MCP got the
same treatment through the same shared pieces, and the full-codebase review
found that NONE of its three seams had a test of its own. Each fails silently,
and only in the shell:

- the flow handler not writing the marker → every MCP return lands in a browser;
- the probe reading the CONNECTOR namespace instead of MCP's own → same outcome,
  because the state is never found where it looked;
- the callback ignoring ``is_native`` → same outcome again, one layer later.

Three seams, one symptom, zero error anywhere — which is exactly the profile
that earns each seam its own direct test.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.core.constants import MCP_USER_OAUTH_STATE_REDIS_PREFIX
from src.core.native_client import native_client_scope
from src.core.oauth.flow_handler import NATIVE_FLOW_METADATA_KEY
from src.domains.user_mcp.router import mcp_return_is_native, oauth_callback

pytestmark = pytest.mark.unit


class TestTheFlowRemembersTheShell:
    """`MCPOAuthFlowHandler.initiate_flow` writes the marker it will need."""

    async def _stored_state(self, *, native: bool) -> dict:
        from src.infrastructure.mcp.oauth_flow import MCPOAuthFlowHandler

        handler = MCPOAuthFlowHandler()
        stored: dict = {}

        async def capture(state: str, data: dict) -> None:
            stored.update(data)

        # cached_metadata and client_id short-circuit discovery and dynamic
        # registration, so the flow reaches its state write without a network.
        # The callback base URL is deployment config the test must supply.
        with (
            patch.object(MCPOAuthFlowHandler, "_store_state", side_effect=capture),
            patch(
                "src.infrastructure.mcp.oauth_flow.settings.mcp_user_oauth_callback_base_url",
                "https://api.test",
            ),
            # The endpoint gate resolves DNS for real (SEC-008) and has its own
            # tests; this one is about the marker, not about name resolution.
            patch.object(
                MCPOAuthFlowHandler, "_is_safe_endpoint", new=AsyncMock(return_value=True)
            ),
            native_client_scope(native),
        ):
            await handler.initiate_flow(
                server_id=__import__("uuid").uuid4(),
                user_id=__import__("uuid").uuid4(),
                mcp_url="https://mcp.example.com/sse",
                cached_metadata={
                    "authorization_endpoint": "https://auth.example.com/authorize",
                    "token_endpoint": "https://auth.example.com/token",
                    "code_challenge_methods_supported": ["S256"],
                },
                client_id="client-abc",
            )
        return stored

    async def test_a_shell_flow_is_marked(self) -> None:
        stored = await self._stored_state(native=True)

        assert stored[NATIVE_FLOW_METADATA_KEY] is True

    async def test_a_browser_flow_carries_no_marker(self) -> None:
        stored = await self._stored_state(native=False)

        # Absent, not False — a field that exists is a field someone reads
        # loosely, and the failure is a desktop user sent to a lia:// link.
        assert NATIVE_FLOW_METADATA_KEY not in stored


class TestTheProbeReadsMcpOwnNamespace:
    """MCP keeps its own Redis prefix, and the probe must look THERE."""

    async def test_the_key_carries_the_mcp_prefix(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps({NATIVE_FLOW_METADATA_KEY: True}).encode())

        with patch(
            "src.core.oauth.state_peek.get_redis_session",
            new=AsyncMock(return_value=redis),
        ):
            verdict = await mcp_return_is_native("state-1")

        # Reading the connector namespace here would answer "not native" for
        # every MCP flow — silently, and only in the shell.
        assert redis.get.await_args.args[0] == f"{MCP_USER_OAUTH_STATE_REDIS_PREFIX}state-1"
        assert verdict is True

    async def test_an_unknown_state_is_a_browser(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        with patch(
            "src.core.oauth.state_peek.get_redis_session",
            new=AsyncMock(return_value=redis),
        ):
            assert await mcp_return_is_native("state-1") is False


class TestTheCallbackComesHome:
    """The refusal path branches on the surface, before any handler runs."""

    async def test_a_native_denial_lands_on_the_shell(self) -> None:
        response = await oauth_callback(error="access_denied", is_native=True)

        location = response.headers["location"]
        assert location.startswith("lia://mcp-callback?")
        assert "mcp_oauth=denied" in location

    async def test_a_browser_denial_is_untouched(self) -> None:
        response = await oauth_callback(error="access_denied", is_native=False)

        assert response.headers["location"].startswith("http")
        assert "mcp_oauth=denied" in response.headers["location"]
