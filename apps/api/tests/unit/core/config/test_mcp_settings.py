"""MCP settings: the per-user server ceiling an operator may raise, within its bound."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.mcp import MCPSettings
from src.core.constants import MCP_USER_MAX_SERVERS_PER_USER_MAX

pytestmark = pytest.mark.unit


def test_an_operator_may_raise_the_per_user_server_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Measured 2026-10-01: production set 50 and the API refused to boot on a bound of 20.
    monkeypatch.setenv("MCP_USER_MAX_SERVERS_PER_USER", "50")
    assert MCPSettings(_env_file=None).mcp_user_max_servers_per_user == 50


@pytest.mark.parametrize("value", [0, MCP_USER_MAX_SERVERS_PER_USER_MAX + 1])
def test_the_ceiling_keeps_a_bound(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    monkeypatch.setenv("MCP_USER_MAX_SERVERS_PER_USER", str(value))
    with pytest.raises(ValidationError):
        MCPSettings(_env_file=None)
