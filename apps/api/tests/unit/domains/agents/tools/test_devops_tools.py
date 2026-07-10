"""Unit tests for DevOps tools (claude_server_task_tool).

Tests server resolution, error handling, tool output formatting, and the
per-user rate limit (anti-runaway ceiling for a paid Claude CLI call).
SSH execution is mocked — no actual connections needed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.tools import devops_tools
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.devops_tools import (
    _get_available_servers,
    _resolve_server,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker


class TestResolveServer:
    """Tests for _resolve_server helper."""

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_resolve_existing_server(self, mock_settings: MagicMock) -> None:
        """Resolve a server that exists in configuration."""
        mock_settings.return_value.devops_servers = json.dumps(
            [
                {"name": "dev", "host": "local", "username": "dev-user"},
                {"name": "prod", "host": "local", "username": "deploy"},
            ]
        )

        config, name = _resolve_server("dev")
        assert config is not None
        assert config["name"] == "dev"
        assert name == "dev"

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_resolve_nonexistent_server(self, mock_settings: MagicMock) -> None:
        """Return None for unknown server name."""
        mock_settings.return_value.devops_servers = json.dumps(
            [
                {"name": "dev", "host": "local", "username": "dev-user"},
            ]
        )

        config, name = _resolve_server("staging")
        assert config is None
        assert name == "staging"

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_resolve_empty_servers(self, mock_settings: MagicMock) -> None:
        """Return None when no servers configured."""
        mock_settings.return_value.devops_servers = "[]"

        config, name = _resolve_server("dev")
        assert config is None

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_resolve_default_server(self, mock_settings: MagicMock) -> None:
        """Default to first server when no name specified."""
        mock_settings.return_value.devops_servers = json.dumps(
            [
                {"name": "dev", "host": "local"},
                {"name": "prod", "host": "local"},
            ]
        )

        config, name = _resolve_server("")
        assert config is not None
        assert config["name"] == "dev"
        assert name == "dev"

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_resolve_default_empty_config(self, mock_settings: MagicMock) -> None:
        """Return None when defaulting but no servers configured."""
        mock_settings.return_value.devops_servers = "[]"

        config, name = _resolve_server("")
        assert config is None


class TestGetAvailableServers:
    """Tests for _get_available_servers helper."""

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_list_available_servers(self, mock_settings: MagicMock) -> None:
        """Return list of configured server names."""
        mock_settings.return_value.devops_servers = json.dumps(
            [
                {"name": "dev", "host": "h1", "username": "u1"},
                {"name": "prod", "host": "h2", "username": "u2"},
            ]
        )

        result = _get_available_servers()
        assert result == ["dev", "prod"]

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_empty_servers_list(self, mock_settings: MagicMock) -> None:
        """Return empty list when no servers configured."""
        mock_settings.return_value.devops_servers = "[]"

        result = _get_available_servers()
        assert result == []


class TestClaudeServerTaskRateLimit:
    """claude_server_task_tool is a paid Claude CLI run + real server actions:
    exceeding the settings-driven threshold must short-circuit with the
    standard ``rate_limit_exceeded`` payload (tool-layer materialization of
    ``ToolErrorCode.RATE_LIMIT_EXCEEDED``). The admin check is mocked so the
    body returns fast without DB access — the limiter records each call
    *before* the body runs, so the blocked/allowed transition is exercised.
    """

    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        """Isolate the in-memory sliding-window tracker between tests."""
        _rate_limit_tracker.clear()
        yield
        _rate_limit_tracker.clear()

    @pytest.mark.asyncio
    async def test_exceeding_threshold_returns_rate_limit_exceeded(self) -> None:
        """Call N+1 within the window is blocked with the standard payload."""
        fake_settings = MagicMock()
        fake_settings.rate_limit_enabled = True
        fake_settings.devops_rate_limit_calls = 2
        fake_settings.devops_rate_limit_window = 60
        max_calls = fake_settings.devops_rate_limit_calls

        runtime = MagicMock()
        runtime.config = {"configurable": {"user_id": "devops-rate-limit-user"}}

        with (
            # The decorator lambdas resolve get_settings from the tool module;
            # the rate_limit wrapper re-imports it from src.core.config.
            patch.object(devops_tools, "get_settings", return_value=fake_settings),
            patch("src.core.config.get_settings", return_value=fake_settings),
            patch.object(devops_tools, "_check_user_is_admin", AsyncMock(return_value=False)),
            patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"),
        ):
            # Under the threshold: the limiter lets every call through to the
            # tool body (which returns a structured FORBIDDEN failure).
            for _ in range(max_calls):
                result = await devops_tools.claude_server_task_tool.coroutine(
                    task="check disk usage", runtime=runtime
                )
                assert isinstance(result, UnifiedToolOutput)

            # Call N+1: blocked by the limiter before the body runs.
            blocked = await devops_tools.claude_server_task_tool.coroutine(
                task="check disk usage", runtime=runtime
            )

            assert isinstance(blocked, str), "rate-limited call must not reach the body"
            payload = json.loads(blocked)
            assert payload["error"] == ToolErrorCode.RATE_LIMIT_EXCEEDED.value.lower()
            assert payload["retry_after_seconds"] > 0
            assert str(max_calls) in payload["limit"]
