"""A linked external callback cannot use the historical unconditional token writer."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.user_mcp import router as module
from src.infrastructure.mcp.personal_oauth_contract import (
    MCPApplicationOAuthCallbacks,
    configure_application_mcp_oauth,
)


@pytest.mark.parametrize("scenario", ["staged", "stage_failure", "denied"])
@pytest.mark.parametrize("native", [False, True])
async def test_linked_callback_stages_or_closes_but_never_persists(monkeypatch, scenario, native):
    server, owner, command = uuid4(), uuid4(), uuid4()
    handler = AsyncMock()
    handler.__aenter__.return_value = handler
    handler.application_command_id = command
    handler.handle_callback.return_value = server, owner, "encrypted-private-token"
    factory = MagicMock(return_value=handler)
    factory._consume_state = AsyncMock(return_value={"application_command_id": str(command)})
    monkeypatch.setattr(module, "MCPOAuthFlowHandler", factory)
    writer = AsyncMock()
    monkeypatch.setattr(module.UserMCPServerService, "update_oauth_credentials", writer)
    callbacks = MCPApplicationOAuthCallbacks(AsyncMock(), AsyncMock(), AsyncMock())
    if scenario == "stage_failure":
        callbacks.stage.side_effect = RuntimeError("private-provider-token")
    previous = configure_application_mcp_oauth(callbacks)
    try:
        response = await module.oauth_callback(
            code="private-code" if scenario != "denied" else None,
            state="private-state",
            error="access_denied" if scenario == "denied" else None,
            is_native=native,
        )
        assert "private" not in response.headers["location"]
        writer.assert_not_awaited()
        if scenario == "staged":
            callbacks.stage.assert_awaited_once_with(
                server, owner, command, "encrypted-private-token"
            )
            assert "mcp_oauth=pending" in response.headers["location"]
            assert ("lia://mcp-callback?" if native else "/dashboard/chat?") in response.headers[
                "location"
            ]
            callbacks.fail.assert_not_awaited()
        else:
            callbacks.fail.assert_awaited_once_with(command)
    finally:
        configure_application_mcp_oauth(previous)
