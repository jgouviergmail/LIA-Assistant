"""
Unit tests for persist_embedding_tokens() conversation tracker integration (v3.3).

Tests the dual-strategy approach:
1. Record into conversation's TrackingContext when available (debug panel visibility)
2. Fallback to standalone TrackingContext when no conversation tracker exists
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.llm.embedding_context import persist_embedding_tokens


@pytest.mark.asyncio
class TestPersistEmbeddingTokensConversationTracker:
    """Tests for Strategy 1: using conversation's TrackingContext."""

    async def test_uses_conversation_tracker_when_available(self) -> None:
        """Records embedding tokens into conversation tracker via current_tracker."""
        mock_tracker = AsyncMock()
        mock_tracker.run_id = "conv-run-123"

        with patch("src.core.context.current_tracker") as mock_ctx_var:
            mock_ctx_var.get.return_value = mock_tracker

            await persist_embedding_tokens(
                model_name="text-embedding-3-small",
                token_count=150,
                cost_usd=0.000003,
                operation="embed_query",
                duration_ms=120.5,
            )

        mock_tracker.record_node_tokens.assert_called_once_with(
            node_name="embedding_embed_query",
            model_name="text-embedding-3-small",
            prompt_tokens=150,
            completion_tokens=0,
            cached_tokens=0,
            duration_ms=120.5,
            call_type="embedding",
        )

    async def test_passes_duration_ms(self) -> None:
        """duration_ms is correctly forwarded to record_node_tokens."""
        mock_tracker = AsyncMock()
        mock_tracker.run_id = "conv-run-456"

        with patch("src.core.context.current_tracker") as mock_ctx_var:
            mock_ctx_var.get.return_value = mock_tracker

            await persist_embedding_tokens(
                model_name="text-embedding-3-small",
                token_count=100,
                cost_usd=0.000002,
                operation="embed_documents",
                duration_ms=250.0,
            )

        call_kwargs = mock_tracker.record_node_tokens.call_args.kwargs
        assert call_kwargs["duration_ms"] == 250.0
        assert call_kwargs["node_name"] == "embedding_embed_documents"

    async def test_graceful_degradation_on_tracker_error(self) -> None:
        """Does not raise when record_node_tokens fails."""
        mock_tracker = AsyncMock()
        mock_tracker.run_id = "conv-run-789"
        mock_tracker.record_node_tokens.side_effect = RuntimeError("lock failure")

        with patch("src.core.context.current_tracker") as mock_ctx_var:
            mock_ctx_var.get.return_value = mock_tracker

            # Should NOT raise - graceful degradation
            await persist_embedding_tokens(
                model_name="text-embedding-3-small",
                token_count=100,
                cost_usd=0.000002,
                operation="embed_query",
                duration_ms=50.0,
            )

        # Verify it was attempted
        mock_tracker.record_node_tokens.assert_called_once()

    async def test_does_not_fall_through_to_strategy_2_on_error(self) -> None:
        """After Strategy 1 fails, does NOT create standalone TrackingContext."""
        mock_tracker = AsyncMock()
        mock_tracker.run_id = "conv-run-err"
        mock_tracker.record_node_tokens.side_effect = RuntimeError("boom")

        with (
            patch("src.core.context.current_tracker") as mock_ctx_var,
            patch("src.infrastructure.llm.embedding_context.get_embedding_context") as mock_get_ctx,
        ):
            mock_ctx_var.get.return_value = mock_tracker
            mock_get_ctx.return_value = MagicMock()  # Would be used by Strategy 2

            await persist_embedding_tokens(
                model_name="text-embedding-3-small",
                token_count=100,
                cost_usd=0.000002,
                operation="embed_query",
            )

        # get_embedding_context should NOT be called (Strategy 1 returns)
        mock_get_ctx.assert_not_called()

    async def test_skips_zero_token_operations(self) -> None:
        """Zero-token operations are skipped entirely."""
        with patch("src.core.context.current_tracker") as mock_ctx_var:
            mock_ctx_var.get.return_value = AsyncMock()

            await persist_embedding_tokens(
                model_name="text-embedding-3-small",
                token_count=0,
                cost_usd=0.0,
                operation="embed_query",
            )

        # current_tracker.get() should not even be called
        mock_ctx_var.get.assert_not_called()


@pytest.mark.asyncio
class TestPersistEmbeddingTokensFallback:
    """Tests for Strategy 2: standalone TrackingContext fallback."""

    async def test_falls_back_when_no_conversation_tracker(self) -> None:
        """Uses embedding_context when current_tracker is None."""
        with (
            patch("src.core.context.current_tracker") as mock_ctx_var,
            patch("src.infrastructure.llm.embedding_context.get_embedding_context") as mock_get_ctx,
        ):
            mock_ctx_var.get.return_value = None
            mock_get_ctx.return_value = None  # No embedding context either

            await persist_embedding_tokens(
                model_name="text-embedding-3-small",
                token_count=100,
                cost_usd=0.000002,
                operation="embed_query",
            )

        # Should have checked embedding_context as fallback
        mock_get_ctx.assert_called_once()

    async def test_skips_when_no_context_at_all(self) -> None:
        """No persistence when both current_tracker and embedding_context are None."""
        with (
            patch("src.core.context.current_tracker") as mock_ctx_var,
            patch("src.infrastructure.llm.embedding_context.get_embedding_context") as mock_get_ctx,
        ):
            mock_ctx_var.get.return_value = None
            mock_get_ctx.return_value = None

            # Should not raise
            await persist_embedding_tokens(
                model_name="text-embedding-3-small",
                token_count=100,
                cost_usd=0.000002,
                operation="embed_query",
            )
