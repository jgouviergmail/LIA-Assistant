"""Unit tests for DevOps tools (claude_server_task_tool).

Tests server resolution, error handling, and tool output formatting.
SSH execution is mocked — no actual connections needed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.domains.agents.tools.devops_tools import (
    _get_available_servers,
    _resolve_server,
)


class TestResolveServer:
    """Tests for _resolve_server helper."""

    @patch("src.domains.agents.tools.devops_tools.get_settings")
    def test_resolve_existing_server(self, mock_settings: MagicMock) -> None:
        """Resolve a server that exists in configuration."""
        mock_settings.return_value.devops_servers = json.dumps(
            [
                {"name": "dev", "host": "local", "username": "jgo"},
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
                {"name": "dev", "host": "local", "username": "jgo"},
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
