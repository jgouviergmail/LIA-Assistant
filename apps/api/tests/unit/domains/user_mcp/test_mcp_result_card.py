"""Tests for McpResultCard component — MCP tool result HTML card."""

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.mcp_result_card import McpResultCard


@pytest.fixture
def card() -> McpResultCard:
    return McpResultCard()


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext()


class TestMcpResultCardRender:
    """Tests for basic card rendering."""

    def test_render_basic(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should render card with tool name, server name, and text result."""
        data = {
            "tool_name": "search_models",
            "server_name": "HuggingFace Hub",
            "result": "Found 42 models matching 'llama'",
        }
        html = card.render(data, ctx)

        assert "lia-card" in html
        assert "lia-mcp" in html
        assert "HuggingFace Hub" in html
        assert "Search Models" in html  # Humanized tool name
        assert "Found 42 models" in html

    def test_render_json_content(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should detect JSON and render in <pre> block."""
        data = {
            "tool_name": "get_info",
            "server_name": "API Server",
            "result": '{"status": "ok", "count": 5}',
        }
        html = card.render(data, ctx)

        assert "<pre" in html
        assert "lia-mcp__content--json" in html
        assert "&quot;status&quot;" in html  # Escaped JSON

    def test_render_json_array(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should detect JSON array and render in <pre> block."""
        data = {
            "tool_name": "list_items",
            "server_name": "Data Server",
            "result": '[{"id": 1}, {"id": 2}]',
        }
        html = card.render(data, ctx)

        assert "<pre" in html
        assert "lia-mcp__content--json" in html

    def test_render_long_text_truncated(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should truncate plain text exceeding 2000 chars."""
        long_text = "A" * 3000
        data = {
            "tool_name": "get_log",
            "server_name": "Log Server",
            "result": long_text,
        }
        html = card.render(data, ctx)

        # truncate(text, 2000) adds "…" at end
        assert len(html) < len(long_text) + 500  # Card overhead
        assert "A" * 2000 not in html  # Should be truncated

    def test_render_html_escaped(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should escape HTML in result to prevent XSS."""
        data = {
            "tool_name": "get_page",
            "server_name": "Web",
            "result": '<script>alert("xss")</script>',
        }
        html = card.render(data, ctx)

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_render_empty_result(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should render card with empty content when result is empty."""
        data = {
            "tool_name": "no_output_tool",
            "server_name": "Silent Server",
            "result": "",
        }
        html = card.render(data, ctx)

        assert "lia-card" in html
        assert "No Output Tool" in html  # Humanized
        assert "Silent Server" in html

    def test_render_with_wrapper(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should wrap with response container by default."""
        data = {
            "tool_name": "test_tool",
            "server_name": "Test",
            "result": "hello",
        }
        html = card.render(data, ctx, with_wrapper=True)

        assert "lia-response" in html

    def test_render_without_wrapper(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should render bare card without wrapper when requested."""
        data = {
            "tool_name": "test_tool",
            "server_name": "Test",
            "result": "hello",
        }
        html = card.render(data, ctx, with_wrapper=False)

        assert "lia-response" not in html
        assert "lia-card" in html

    def test_render_server_name_in_badge(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should display server name in badge with MCP prefix."""
        data = {
            "tool_name": "ping",
            "server_name": "My Custom Server",
            "result": "pong",
        }
        html = card.render(data, ctx)

        assert "MCP" in html
        assert "My Custom Server" in html
        assert "lia-badge" in html

    def test_render_newlines_converted_to_br(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should convert newlines to <br> in plain text content."""
        data = {
            "tool_name": "multi_line",
            "server_name": "Test",
            "result": "line1\nline2\nline3",
        }
        html = card.render(data, ctx)

        assert "line1<br>line2<br>line3" in html


class TestMcpResultCardRenderList:
    """Tests for render_list() with multiple MCP items."""

    def test_render_list_multiple_items(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should render multiple MCP items as a list."""
        items = [
            {
                "tool_name": "search",
                "server_name": "Server A",
                "result": "result 1",
            },
            {
                "tool_name": "fetch",
                "server_name": "Server B",
                "result": "result 2",
            },
            {
                "tool_name": "analyze",
                "server_name": "Server C",
                "result": "result 3",
            },
        ]
        html = card.render_list(items, ctx)

        assert "Server A" in html
        assert "Server B" in html
        assert "Server C" in html
        assert "result 1" in html
        assert "result 2" in html
        assert "result 3" in html

    def test_render_list_single_item(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should render single item in list mode."""
        items = [
            {
                "tool_name": "ping",
                "server_name": "Solo",
                "result": "pong",
            },
        ]
        html = card.render_list(items, ctx)

        assert "Solo" in html
        assert "pong" in html


class TestMcpResultCardStructuredRendering:
    """Tests for structured MCP item rendering (evolution F2.4)."""

    def test_render_structured_item(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should render structured card with auto-detected title and fields."""
        data = {
            "tool_name": "search_repositories",
            "server_name": "GitHub",
            "_mcp_structured": True,
            "name": "LIA",
            "description": "AI assistant with multi-agent orchestration",
            "stargazers_count": 12,
            "language": "Python",
        }
        html = card.render(data, ctx, with_wrapper=False)

        assert "lia-card" in html
        assert "lia-mcp" in html
        assert "GitHub" in html
        # Title should be auto-detected from "name" field
        assert "LIA" in html
        # Description should be rendered
        assert "AI assistant" in html
        # Detail fields should appear
        assert "Stargazers Count" in html
        assert "12" in html
        assert "Language" in html
        assert "Python" in html

    def test_render_structured_item_title_fallback(
        self, card: McpResultCard, ctx: RenderContext
    ) -> None:
        """Should fallback to humanised tool_name when no title field found."""
        data = {
            "tool_name": "get_metrics",
            "server_name": "Monitor",
            "_mcp_structured": True,
            "cpu": 85,
            "memory": 4096,
        }
        html = card.render(data, ctx, with_wrapper=False)

        # Fallback title from tool_name
        assert "Get Metrics" in html

    def test_render_structured_excludes_internal_fields(
        self, card: McpResultCard, ctx: RenderContext
    ) -> None:
        """Should not render internal fields like _mcp_structured, url, node_id."""
        data = {
            "tool_name": "search_repos",
            "server_name": "GitHub",
            "_mcp_structured": True,
            "_registry_id": "mcp_abc123",
            "name": "MyRepo",
            "url": "https://github.com/user/repo",
            "node_id": "MDEwOlJlcG9zaXRvcnkxMjM=",
            "language": "Python",
        }
        html = card.render(data, ctx, with_wrapper=False)

        assert "MyRepo" in html
        assert "Python" in html
        # Internal fields should not appear
        assert "_mcp_structured" not in html
        assert "_registry_id" not in html
        assert "node_id" not in html.lower().replace("node id", "")
        # url should be excluded from details
        assert "https://github.com" not in html

    def test_render_raw_unchanged(self, card: McpResultCard, ctx: RenderContext) -> None:
        """Should use raw rendering when _mcp_structured is absent."""
        data = {
            "tool_name": "ping",
            "server_name": "Test",
            "result": "pong response",
        }
        html = card.render(data, ctx, with_wrapper=False)

        # Should render raw content, not structured
        assert "pong response" in html
        assert "Ping" in html  # Humanised tool name as title
        assert "lia-mcp__content" in html  # Raw content div
