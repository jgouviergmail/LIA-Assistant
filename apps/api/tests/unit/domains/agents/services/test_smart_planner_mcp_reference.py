"""
Unit tests for SmartPlannerService._build_mcp_reference().

Tests the MCP reference documentation injection into planner prompts,
including content formatting, truncation, domain filtering, and dedup.
Personal servers' references are collected at real use (M1b, spec §5.5b):
each test hands the planner a source whose reference this worker already holds.

Phase: evolution F2.6 — MCP Apps
Created: 2026-03-05
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.services.smart_planner_service import SmartPlannerService
from tests.helpers.mcp_reference_sources import reference_context, reference_source

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)


def _sources(**references: str) -> dict[str, object]:
    return {
        name: reference_source(f"mcp_{name}", reference=text, fetched_at=NOW)
        for name, text in references.items()
    }


class TestBuildMcpReference:
    """Test MCP reference documentation builder."""

    async def test_empty_when_no_domains(self):
        """Returns empty string when no domains are passed."""
        assert await SmartPlannerService._build_mcp_reference() == ""
        assert await SmartPlannerService._build_mcp_reference([]) == ""

    async def test_empty_when_no_mcp_domains(self):
        """Returns empty string when domains don't include any MCP domain."""
        with reference_context(_sources(excalidraw="Some content")):
            result = await SmartPlannerService._build_mcp_reference(["weather", "email"])
        assert result == ""

    async def test_formats_single_server_reference(self):
        """Single server read_me content should be formatted with MANDATORY header."""
        with reference_context(_sources(excalidraw="Use JSON arrays for elements.")):
            result = await SmartPlannerService._build_mcp_reference(["mcp_excalidraw"])
        assert "MCP TOOL FORMAT REFERENCE — excalidraw (MANDATORY)" in result
        assert "Use JSON arrays for elements." in result
        assert "you MUST follow the exact structure" in result

    async def test_formats_multiple_servers(self):
        """Multiple servers should each get their own section."""
        sources = _sources(excalidraw="Excalidraw format docs", figma="Figma format docs")
        with reference_context(sources):
            result = await SmartPlannerService._build_mcp_reference(["mcp_excalidraw", "mcp_figma"])
        assert "MCP TOOL FORMAT REFERENCE — excalidraw (MANDATORY)" in result
        assert "MCP TOOL FORMAT REFERENCE — figma (MANDATORY)" in result
        assert "Excalidraw format docs" in result
        assert "Figma format docs" in result

    async def test_only_selected_mcp_domains_included(self):
        """Only servers matching selected domains should be included."""
        with reference_context(_sources(excalidraw="Excalidraw docs", figma="Figma docs")):
            result = await SmartPlannerService._build_mcp_reference(["mcp_excalidraw"])
        assert "excalidraw" in result
        assert "Figma docs" not in result

    async def test_truncation_line_aware(self):
        """Truncation should cut at last complete line boundary."""
        long_content = "\n".join(f"Line {i}: some content here" for i in range(100))
        with (
            reference_context(_sources(test_server=long_content)),
            patch("src.core.config.get_settings") as mock,
        ):
            mock.return_value = type("S", (), {"mcp_reference_content_max_chars": 200})()
            result = await SmartPlannerService._build_mcp_reference(["mcp_test_server"])

        assert "... (truncated)" in result
        for line in result.split("\n"):
            if line.startswith("Line "):
                assert ": some content here" in line

    async def test_empty_when_max_chars_zero(self):
        """Returns empty string — and fetches nothing — when max_chars setting is 0."""
        collect = AsyncMock(return_value={"test": "Some content"})
        with (
            patch(
                "src.domains.agents.services.planner.mcp_reference.collect_user_references",
                new=collect,
            ),
            patch("src.core.config.get_settings") as mock,
        ):
            mock.return_value = type("S", (), {"mcp_reference_content_max_chars": 0})()
            result = await SmartPlannerService._build_mcp_reference(["mcp_test"])
        assert result == ""
        collect.assert_not_awaited()

    async def test_no_truncation_when_under_limit(self):
        """Short content should not be truncated."""
        with reference_context(_sources(test="Short content")):
            result = await SmartPlannerService._build_mcp_reference(["mcp_test"])
        assert "... (truncated)" not in result
        assert "Short content" in result

    async def test_catalogue_cross_reference_instruction(self):
        """Output should instruct LLM to match catalogue parameter names."""
        with reference_context(_sources(test="Format: {elements: [...]}")):
            result = await SmartPlannerService._build_mcp_reference(["mcp_test"])
        assert "Match parameter names from the catalogue above" in result

    async def test_admin_mcp_takes_priority_over_user(self):
        """Admin MCP reference wins over user MCP for the same server."""
        # ADR-062: the admin manager is also asked for server_configs to
        # detect iterative_mode servers (skipped from reference content).
        # An empty mapping keeps the iterative-skip branch a no-op.
        admin = type(
            "M",
            (),
            {"reference_content": {"excalidraw": "ADMIN content"}, "server_configs": {}},
        )()
        with (
            reference_context(_sources(excalidraw="USER content")),
            patch(
                "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
                return_value=admin,
            ),
        ):
            result = await SmartPlannerService._build_mcp_reference(["mcp_excalidraw"])

        assert "ADMIN content" in result
        assert "USER content" not in result

    async def test_user_only_when_admin_manager_none(self):
        """User MCP reference is used when admin MCP manager is None."""
        with (
            reference_context(_sources(test_server="User-only content")),
            patch(
                "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
                return_value=None,
            ),
        ):
            result = await SmartPlannerService._build_mcp_reference(["mcp_test_server"])

        assert "User-only content" in result
        assert "MCP TOOL FORMAT REFERENCE — test_server (MANDATORY)" in result
