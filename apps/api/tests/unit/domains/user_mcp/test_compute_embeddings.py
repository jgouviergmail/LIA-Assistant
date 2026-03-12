"""Tests for compute_tool_embeddings function."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.services.tool_selector import compute_tool_embeddings


class TestComputeToolEmbeddings:
    """Tests for compute_tool_embeddings module-level function."""

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.tool_selector.get_tool_selector")
    async def test_returns_empty_when_not_initialized(self, mock_get_selector) -> None:
        """Should return empty dict when selector is not initialized."""
        selector = MagicMock()
        selector._initialized = False
        selector._embeddings = None
        mock_get_selector.return_value = selector

        result = await compute_tool_embeddings(
            tool_metadata=[{"name": "test", "description": "Test tool"}],
            server_name="TestServer",
        )
        assert result == {}

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.tool_selector.get_tool_selector")
    async def test_returns_empty_for_empty_metadata(self, mock_get_selector) -> None:
        """Should return empty dict when no tools provided."""
        selector = MagicMock()
        selector._initialized = True
        selector._embeddings = MagicMock()
        mock_get_selector.return_value = selector

        result = await compute_tool_embeddings(
            tool_metadata=[],
            server_name="TestServer",
        )
        assert result == {}

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.tool_selector.get_tool_selector")
    async def test_computes_description_and_keyword_embeddings(self, mock_get_selector) -> None:
        """Should compute both description and keyword embeddings for each tool."""
        mock_embeddings = AsyncMock()
        # Tool has description "Search models" → 1 desc + keywords: [server, name, "Search", "models"]
        # "Search" is 6 chars (>3), "models" is 6 chars (>3)
        # Keywords: "TestServer", "hub_search", "Search", "models" = 4 keywords
        # Total texts: 1 (desc) + 4 (keywords) = 5
        mock_embeddings.aembed_documents = AsyncMock(
            return_value=[
                [0.1, 0.2, 0.3],  # description: "Search models"
                [0.4, 0.5, 0.6],  # keyword: "TestServer"
                [0.7, 0.8, 0.9],  # keyword: "hub_search"
                [1.0, 1.1, 1.2],  # keyword: "Search"
                [1.3, 1.4, 1.5],  # keyword: "models"
            ]
        )

        selector = MagicMock()
        selector._initialized = True
        selector._embeddings = mock_embeddings
        mock_get_selector.return_value = selector

        result = await compute_tool_embeddings(
            tool_metadata=[
                {"name": "hub_search", "description": "Search models"},
            ],
            server_name="TestServer",
        )

        assert "hub_search" in result
        assert result["hub_search"]["description"] == [0.1, 0.2, 0.3]
        assert len(result["hub_search"]["keywords"]) == 4
        assert "keyword_names" in result["hub_search"]
        assert result["hub_search"]["keyword_names"][0] == "TestServer"

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.tool_selector.get_tool_selector")
    async def test_multiple_tools_batch_embed(self, mock_get_selector) -> None:
        """Should batch-embed all tools in a single call."""
        mock_embeddings = AsyncMock()

        # Dynamically return correct number of embeddings
        def _dynamic_embed(texts: list[str]) -> list[list[float]]:
            return [[i * 0.1] * 3 for i in range(len(texts))]

        mock_embeddings.aembed_documents = AsyncMock(side_effect=_dynamic_embed)

        selector = MagicMock()
        selector._initialized = True
        selector._embeddings = mock_embeddings
        mock_get_selector.return_value = selector

        result = await compute_tool_embeddings(
            tool_metadata=[
                {"name": "tool_a", "description": "First tool desc"},
                {"name": "tool_b", "description": "Second tool desc"},
            ],
            server_name="MyServer",
        )

        # Both tools should have embeddings
        assert "tool_a" in result
        assert "tool_b" in result
        # Single batch call
        mock_embeddings.aembed_documents.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.tool_selector.get_tool_selector")
    async def test_tool_without_description(self, mock_get_selector) -> None:
        """Should still compute keyword embeddings when description is empty."""
        mock_embeddings = AsyncMock()
        # Only keyword embeddings: "TestServer", "empty_tool" = 2 keywords
        mock_embeddings.aembed_documents = AsyncMock(
            return_value=[
                [0.1, 0.2, 0.3],  # keyword: "TestServer"
                [0.4, 0.5, 0.6],  # keyword: "empty_tool"
            ]
        )

        selector = MagicMock()
        selector._initialized = True
        selector._embeddings = mock_embeddings
        mock_get_selector.return_value = selector

        result = await compute_tool_embeddings(
            tool_metadata=[
                {"name": "empty_tool", "description": ""},
            ],
            server_name="TestServer",
        )

        assert "empty_tool" in result
        # No description embedding
        assert "description" not in result["empty_tool"]
        # Should have keyword embeddings
        assert "keywords" in result["empty_tool"]

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.tool_selector.get_tool_selector")
    async def test_strips_markdown_from_description(self, mock_get_selector) -> None:
        """Should strip markdown bold from description for clean embedding."""
        mock_embeddings = AsyncMock()
        mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1] * 3 for _ in range(10)])

        selector = MagicMock()
        selector._initialized = True
        selector._embeddings = mock_embeddings
        mock_get_selector.return_value = selector

        await compute_tool_embeddings(
            tool_metadata=[
                {"name": "test", "description": "**Bold Tool** - does things\nDetails here"},
            ],
            server_name="Server",
        )

        # First text should be cleaned first line (no markdown, no second line)
        texts = mock_embeddings.aembed_documents.call_args[0][0]
        # The first text should be the cleaned description (first line without **)
        assert texts[0] == "Bold Tool - does things"
