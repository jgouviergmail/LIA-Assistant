"""
Unit tests for SmartPlannerService._build_mcp_reference().

Tests the MCP reference documentation injection into planner prompts,
including content formatting, truncation, domain filtering, and dedup.

Phase: evolution F2.6 — MCP Apps
Created: 2026-03-05
"""

from unittest.mock import patch

from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.services.smart_planner_service import SmartPlannerService


class TestBuildMcpReference:
    """Test MCP reference documentation builder."""

    def test_empty_when_no_domains(self):
        """Returns empty string when no domains are passed."""
        assert SmartPlannerService._build_mcp_reference() == ""
        assert SmartPlannerService._build_mcp_reference([]) == ""

    def test_empty_when_no_mcp_domains(self):
        """Returns empty string when domains don't include any MCP domain."""
        ctx = UserMCPToolsContext(
            server_reference_content={"excalidraw": "Some content"},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            result = SmartPlannerService._build_mcp_reference(["weather", "email"])
            assert result == ""
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_formats_single_server_reference(self):
        """Single server read_me content should be formatted with MANDATORY header."""
        ctx = UserMCPToolsContext(
            server_reference_content={"excalidraw": "Use JSON arrays for elements."},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            result = SmartPlannerService._build_mcp_reference(["mcp_excalidraw"])
            assert "MCP TOOL FORMAT REFERENCE — excalidraw (MANDATORY)" in result
            assert "Use JSON arrays for elements." in result
            assert "you MUST follow the exact structure" in result
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_formats_multiple_servers(self):
        """Multiple servers should each get their own section."""
        ctx = UserMCPToolsContext(
            server_reference_content={
                "excalidraw": "Excalidraw format docs",
                "figma": "Figma format docs",
            },
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            result = SmartPlannerService._build_mcp_reference(["mcp_excalidraw", "mcp_figma"])
            assert "MCP TOOL FORMAT REFERENCE — excalidraw (MANDATORY)" in result
            assert "MCP TOOL FORMAT REFERENCE — figma (MANDATORY)" in result
            assert "Excalidraw format docs" in result
            assert "Figma format docs" in result
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_only_selected_mcp_domains_included(self):
        """Only servers matching selected domains should be included."""
        ctx = UserMCPToolsContext(
            server_reference_content={
                "excalidraw": "Excalidraw docs",
                "figma": "Figma docs",
            },
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            result = SmartPlannerService._build_mcp_reference(["mcp_excalidraw"])
            assert "excalidraw" in result
            assert "Figma docs" not in result
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_truncation_line_aware(self):
        """Truncation should cut at last complete line boundary."""
        lines = [f"Line {i}: some content here" for i in range(100)]
        long_content = "\n".join(lines)

        ctx = UserMCPToolsContext(
            server_reference_content={"test_server": long_content},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            with patch("src.core.config.get_settings") as mock:
                mock.return_value = type("S", (), {"mcp_reference_content_max_chars": 200})()
                result = SmartPlannerService._build_mcp_reference(["mcp_test_server"])

            assert "... (truncated)" in result
            for line in result.split("\n"):
                if line.startswith("Line "):
                    assert "Line " in line and ": some content here" in line
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_empty_when_max_chars_zero(self):
        """Returns empty string when max_chars setting is 0."""
        ctx = UserMCPToolsContext(
            server_reference_content={"test": "Some content"},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            with patch("src.core.config.get_settings") as mock:
                mock.return_value = type("S", (), {"mcp_reference_content_max_chars": 0})()
                result = SmartPlannerService._build_mcp_reference(["mcp_test"])
            assert result == ""
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_no_truncation_when_under_limit(self):
        """Short content should not be truncated."""
        ctx = UserMCPToolsContext(
            server_reference_content={"test": "Short content"},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            result = SmartPlannerService._build_mcp_reference(["mcp_test"])
            assert "... (truncated)" not in result
            assert "Short content" in result
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_catalogue_cross_reference_instruction(self):
        """Output should instruct LLM to match catalogue parameter names."""
        ctx = UserMCPToolsContext(
            server_reference_content={"test": "Format: {elements: [...]}"},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            result = SmartPlannerService._build_mcp_reference(["mcp_test"])
            assert "Match parameter names from the catalogue above" in result
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_admin_mcp_takes_priority_over_user(self):
        """Admin MCP reference wins over user MCP for the same server."""
        ctx = UserMCPToolsContext(
            server_reference_content={"excalidraw": "USER content"},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            with patch("src.infrastructure.mcp.client_manager.get_mcp_client_manager") as mock_mgr:
                admin = type("M", (), {"reference_content": {"excalidraw": "ADMIN content"}})()
                mock_mgr.return_value = admin
                result = SmartPlannerService._build_mcp_reference(["mcp_excalidraw"])

            assert "ADMIN content" in result
            assert "USER content" not in result
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_user_only_when_admin_manager_none(self):
        """User MCP reference is used when admin MCP manager is None."""
        ctx = UserMCPToolsContext(
            server_reference_content={"test_server": "User-only content"},
        )
        token = user_mcp_tools_ctx.set(ctx)
        try:
            with patch("src.infrastructure.mcp.client_manager.get_mcp_client_manager") as mock_mgr:
                mock_mgr.return_value = None
                result = SmartPlannerService._build_mcp_reference(["mcp_test_server"])

            assert "User-only content" in result
            assert "MCP TOOL FORMAT REFERENCE — test_server (MANDATORY)" in result
        finally:
            user_mcp_tools_ctx.reset(token)
