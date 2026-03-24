"""
Unit tests for read-only tool classification.

Tests infer_tool_category MCP prefix handling and is_read_only_tool.

Phase: ADR-062 — Agent Initiative Phase
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.domains.agents.registry.catalogue import (
    infer_tool_category,
    is_read_only_tool,
)


@pytest.mark.unit
class TestInferToolCategoryMCPPrefix:
    """Tests for MCP prefix stripping in infer_tool_category."""

    def test_mcp_create_view(self) -> None:
        assert infer_tool_category("mcp_excalidraw_create_view") == "create"

    def test_mcp_read_me(self) -> None:
        assert infer_tool_category("mcp_excalidraw_read_me") == "readonly"

    def test_mcp_search_flights(self) -> None:
        assert infer_tool_category("mcp_google_flights_search_flights") == "search"

    def test_mcp_delete_item(self) -> None:
        assert infer_tool_category("mcp_server_delete_item") == "delete"

    def test_mcp_send_message(self) -> None:
        assert infer_tool_category("mcp_slack_send_message") == "send"

    def test_mcp_get_data(self) -> None:
        assert infer_tool_category("mcp_api_get_data") == "search"

    def test_non_mcp_unchanged(self) -> None:
        assert infer_tool_category("get_emails_tool") == "search"
        assert infer_tool_category("create_event_tool") == "create"
        assert infer_tool_category("get_weather_tool") == "readonly"


@pytest.mark.unit
class TestIsReadOnlyTool:
    """Tests for is_read_only_tool helper."""

    def _make_manifest(self, name: str, category: str | None = None) -> MagicMock:
        m = MagicMock()
        m.name = name
        m.tool_category = category
        return m

    def test_search_tool_is_read_only(self) -> None:
        assert is_read_only_tool(self._make_manifest("get_emails_tool"))

    def test_readonly_tool_is_read_only(self) -> None:
        assert is_read_only_tool(self._make_manifest("get_weather_tool"))

    def test_create_tool_is_not_read_only(self) -> None:
        assert not is_read_only_tool(self._make_manifest("create_event_tool"))

    def test_send_tool_is_not_read_only(self) -> None:
        assert not is_read_only_tool(self._make_manifest("send_email_tool"))

    def test_delete_tool_is_not_read_only(self) -> None:
        assert not is_read_only_tool(self._make_manifest("delete_contact_tool"))

    def test_explicit_category_overrides(self) -> None:
        assert is_read_only_tool(self._make_manifest("whatever", category="search"))
        assert not is_read_only_tool(self._make_manifest("whatever", category="create"))

    def test_mcp_create_is_not_read_only(self) -> None:
        assert not is_read_only_tool(self._make_manifest("mcp_excalidraw_create_view"))

    def test_mcp_read_me_is_read_only(self) -> None:
        assert is_read_only_tool(self._make_manifest("mcp_excalidraw_read_me"))
