"""
Unit tests for fallback response service.

Tests for the graceful fallback response generation when the pipeline fails.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.services.fallback_response import (
    SIMPLE_FALLBACK_MESSAGE,
    generate_fallback_response,
    generate_fallback_response_sync,
)


class TestSimpleFallbackMessage:
    """Tests for SIMPLE_FALLBACK_MESSAGE constant."""

    def test_fallback_message_is_french(self):
        """Test that fallback message is in French."""
        assert "Je n'ai pas" in SIMPLE_FALLBACK_MESSAGE

    def test_fallback_message_asks_to_reformulate(self):
        """Test that fallback message asks user to reformulate."""
        assert "reformuler" in SIMPLE_FALLBACK_MESSAGE

    def test_fallback_message_not_empty(self):
        """Test that fallback message is not empty."""
        assert len(SIMPLE_FALLBACK_MESSAGE) > 0


class TestGenerateFallbackResponse:
    """Tests for generate_fallback_response async generator."""

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_fallback_on_llm_error(self, mock_get_llm, mock_load_prompt):
        """Test that simple fallback message is used when LLM fails."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        # Mock LLM to raise exception
        mock_llm = MagicMock()
        mock_llm.astream.side_effect = Exception("LLM error")
        mock_get_llm.return_value = mock_llm

        format_fn = MagicMock(return_value={"type": "token"})

        results = []
        async for chunk, content in generate_fallback_response(
            user_query="test",
            run_id="run_error",
            format_chunk_fn=format_fn,
        ):
            results.append((chunk, content))

        assert len(results) == 1
        assert results[0][1] == SIMPLE_FALLBACK_MESSAGE
        format_fn.assert_called_with(SIMPLE_FALLBACK_MESSAGE)

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_handles_timeout_error(self, mock_get_llm, mock_load_prompt):
        """Test that timeout error falls back gracefully."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        mock_llm = MagicMock()
        mock_llm.astream.side_effect = TimeoutError("Request timed out")
        mock_get_llm.return_value = mock_llm

        format_fn = MagicMock(return_value={"type": "token"})

        results = []
        async for chunk, content in generate_fallback_response(
            user_query="test query",
            run_id="run_timeout",
            format_chunk_fn=format_fn,
        ):
            results.append((chunk, content))

        assert len(results) == 1
        assert results[0][1] == SIMPLE_FALLBACK_MESSAGE

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_handles_connection_error(self, mock_get_llm, mock_load_prompt):
        """Test that connection error falls back gracefully."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        mock_llm = MagicMock()
        mock_llm.astream.side_effect = ConnectionError("Connection refused")
        mock_get_llm.return_value = mock_llm

        format_fn = MagicMock(return_value={"type": "token"})

        results = []
        async for chunk, content in generate_fallback_response(
            user_query="query",
            run_id="run_conn",
            format_chunk_fn=format_fn,
        ):
            results.append((chunk, content))

        assert len(results) == 1
        assert results[0][1] == SIMPLE_FALLBACK_MESSAGE


class TestGenerateFallbackResponseSync:
    """Tests for generate_fallback_response_sync async function."""

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    @patch("src.infrastructure.llm.invoke_helpers.enrich_config_with_node_metadata")
    async def test_returns_complete_response(self, mock_enrich, mock_get_llm, mock_load_prompt):
        """Test that sync version returns complete response."""
        mock_load_prompt.return_value.format.return_value = "prompt text"
        mock_enrich.return_value = {"config": "enriched"}

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = "Complete fallback response"
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        result = await generate_fallback_response_sync(
            user_query="test query",
            run_id="run_sync",
            config={"callbacks": []},
        )

        assert result == "Complete fallback response"

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_fallback_on_llm_error(self, mock_get_llm, mock_load_prompt):
        """Test that simple fallback is returned when LLM fails."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        mock_get_llm.return_value = mock_llm

        result = await generate_fallback_response_sync(
            user_query="test",
            run_id="run_sync_error",
        )

        assert result == SIMPLE_FALLBACK_MESSAGE

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_handles_response_without_content_attr(self, mock_get_llm, mock_load_prompt):
        """Test handling when response doesn't have content attribute."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        # Mock response without content attribute
        mock_response = "string response"
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        result = await generate_fallback_response_sync(
            user_query="test",
            run_id="run_sync_str",
        )

        assert result == "string response"

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_handles_empty_query(self, mock_get_llm, mock_load_prompt):
        """Test handling of empty query."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        mock_response = MagicMock()
        mock_response.content = "Response for empty"
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        result = await generate_fallback_response_sync(
            user_query="",
            run_id="run_sync_empty",
        )

        assert result == "Response for empty"

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_works_without_config(self, mock_get_llm, mock_load_prompt):
        """Test that function works without config."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        mock_response = MagicMock()
        mock_response.content = "No config response"
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        result = await generate_fallback_response_sync(
            user_query="test",
            run_id="run_sync_no_config",
            config=None,
        )

        assert result == "No config response"

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.infrastructure.llm.get_llm")
    async def test_handles_timeout(self, mock_get_llm, mock_load_prompt):
        """Test that timeout is handled gracefully."""
        mock_load_prompt.return_value.format.return_value = "prompt text"

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=TimeoutError("Timeout"))
        mock_get_llm.return_value = mock_llm

        result = await generate_fallback_response_sync(
            user_query="test",
            run_id="run_sync_timeout",
        )

        assert result == SIMPLE_FALLBACK_MESSAGE
