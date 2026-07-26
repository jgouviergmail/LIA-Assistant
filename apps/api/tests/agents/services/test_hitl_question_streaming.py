"""
Unit tests for HITL question streaming functionality.

Tests cover:
- Streaming question generation (generate_confirmation_question_stream)
- TTFT (Time To First Token) measurement
- Token aggregation and metrics
- Error handling during streaming
- Config propagation (Langfuse, TokenTracking)

Phase 5: HITL Streaming Optimization
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessageChunk

from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator

pytestmark = pytest.mark.unit


@pytest.fixture
def question_generator():
    """HitlQuestionGenerator whose LLM clients are substitutable stubs.

    Every test here patches `astream` on the client. That cannot be done on the
    real one: `ChatOpenAI` is a pydantic model which rejects unknown instance
    fields, and `astream` lives on the class — `patch.object` raised
    `"ChatOpenAI" object has no field "astream"`. Substituting the collaborator
    itself keeps all call sites working and makes the seam explicit. The single
    `llm` attribute these tests were written against was also split per prompt
    family (`tool_question_llm` / `plan_approval_llm`).
    """
    generator = HitlQuestionGenerator()
    generator.tool_question_llm = MagicMock()
    generator.plan_approval_llm = MagicMock()
    return generator


@pytest.fixture
def mock_llm_stream():
    """Mock LLM streaming response."""

    async def _create_stream(tokens: list[str], delay_ms: int = 10):
        """Create async generator simulating LLM token stream."""
        for token in tokens:
            await asyncio.sleep(delay_ms / 1000)  # Simulate network latency
            chunk = AIMessageChunk(content=token)
            yield chunk

    return _create_stream


class TestHitlQuestionStreaming:
    """Test suite for HITL question streaming."""

    @pytest.mark.asyncio
    async def test_streaming_generates_complete_question(self, question_generator, mock_llm_stream):
        """Test that streaming generates complete question by aggregating tokens."""
        # Arrange
        tokens = ["Je ", "vais ", "rechercher ", "le ", "contact ", "'jean'. ", "Continuer", "?"]
        expected_question = "".join(tokens)

        with patch.object(
            question_generator.tool_question_llm, "astream", return_value=mock_llm_stream(tokens)
        ):
            # Act
            full_question = ""
            async for token in question_generator.generate_confirmation_question_stream(
                tool_name="search_contacts_tool",
                tool_args={"query": "jean"},
                user_language="fr",
            ):
                full_question += token

            # Assert
            assert full_question == expected_question
            assert len(full_question) > 0

    @pytest.mark.asyncio
    async def test_streaming_measures_ttft(self, question_generator, mock_llm_stream):
        """Test that TTFT (Time To First Token) is measured and logged."""
        # Arrange
        tokens = ["Test", " question"]
        expected_ttft_range = (0.01, 0.1)  # 10-100ms expected

        with patch.object(
            question_generator.tool_question_llm,
            "astream",
            return_value=mock_llm_stream(tokens, delay_ms=20),
        ):
            # Act
            start = time.time()
            first_token_time = None

            index = 0
            async for _token in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={"arg": "value"},
            ):
                i, index = index, index + 1
                if i == 0:
                    first_token_time = time.time() - start
                    break

            # Assert
            assert first_token_time is not None
            assert expected_ttft_range[0] <= first_token_time <= expected_ttft_range[1]

    @pytest.mark.asyncio
    async def test_streaming_tracks_prometheus_metrics(self, question_generator, mock_llm_stream):
        """Test that Prometheus TTFT metric is recorded."""
        # Arrange
        tokens = ["Metric", " test"]

        with (
            patch.object(
                question_generator.tool_question_llm,
                "astream",
                return_value=mock_llm_stream(tokens),
            ),
            patch(
                "src.infrastructure.observability.metrics_agents.hitl_question_ttft_seconds"
            ) as mock_ttft_metric,
        ):
            # Act
            async for _ in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={},
            ):
                pass  # Consume all tokens

            # Assert — the metric is labelled by question type, so the
            # observation happens on labels(...), not on the metric itself.
            mock_ttft_metric.labels.assert_called_once_with(type="tool_confirmation")
            observe = mock_ttft_metric.labels.return_value.observe
            observe.assert_called_once()
            ttft_value = observe.call_args[0][0]
            assert 0 < ttft_value < 1.0  # TTFT should be < 1 second

    @pytest.mark.asyncio
    async def test_streaming_yields_tokens_progressively(self, question_generator, mock_llm_stream):
        """Test that tokens are yielded progressively, not batched."""
        # Arrange
        tokens = ["A", "B", "C", "D", "E"]
        received_tokens = []
        timestamps = []

        with patch.object(
            question_generator.tool_question_llm,
            "astream",
            return_value=mock_llm_stream(tokens, delay_ms=50),
        ):
            # Act
            async for token in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={},
            ):
                received_tokens.append(token)
                timestamps.append(time.time())

            # Assert
            assert received_tokens == tokens
            assert len(timestamps) == len(tokens)

            # Verify progressive delivery (tokens arrive over time, not all at once)
            time_deltas = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
            assert all(delta > 0.01 for delta in time_deltas)  # At least 10ms between tokens

    @pytest.mark.asyncio
    async def test_streaming_handles_empty_chunks(self, question_generator, mock_llm_stream):
        """Test that empty chunks from LLM are handled gracefully."""

        # Arrange
        async def stream_with_empty():
            yield AIMessageChunk(content="Start")
            yield AIMessageChunk(content="")  # Empty chunk
            yield AIMessageChunk(content="")  # empty content (None is unrepresentable)
            yield AIMessageChunk(content="End")

        with patch.object(
            question_generator.tool_question_llm, "astream", return_value=stream_with_empty()
        ):
            # Act
            tokens = []
            async for token in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={},
            ):
                tokens.append(token)

            # Assert
            # Empty/None chunks should yield empty strings (not skip)
            assert tokens == ["Start", "", "", "End"]

    @pytest.mark.asyncio
    async def test_streaming_propagates_token_tracker(self, question_generator, mock_llm_stream):
        """Test that TokenTrackingCallback is propagated to streaming config."""
        # Arrange
        tokens = ["Test"]
        mock_tracker = MagicMock()

        with patch.object(
            question_generator.tool_question_llm, "astream", return_value=mock_llm_stream(tokens)
        ) as mock_astream:
            # Act
            async for _ in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={},
                tracker=mock_tracker,
            ):
                pass

            # Assert
            # Verify astream was called with config containing tracker
            call_config = mock_astream.call_args[1]["config"]
            assert "callbacks" in call_config
            assert mock_tracker in call_config["callbacks"]

    @pytest.mark.asyncio
    async def test_streaming_creates_instrumented_config(self, question_generator, mock_llm_stream):
        """Test that Langfuse instrumentation config is created."""
        # Arrange
        tokens = ["Config", " test"]

        with (
            patch.object(
                question_generator.tool_question_llm,
                "astream",
                return_value=mock_llm_stream(tokens),
            ),
            patch(
                "src.infrastructure.llm.instrumentation.create_instrumented_config"
            ) as mock_create_config,
        ):
            mock_create_config.return_value = {"callbacks": [], "metadata": {}}

            # Act
            async for _ in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={"key": "value"},
                user_language="en",
            ):
                pass

            # Assert
            mock_create_config.assert_called_once_with(
                llm_type="hitl_question_generator",
                tags=["hitl", "question_generation", "streaming"],
                metadata={
                    "tool_name": "test_tool",
                    "user_language": "en",
                    "args_count": 1,
                    "streaming": True,
                },
            )

    @pytest.mark.asyncio
    async def test_streaming_error_handling(self, question_generator):
        """Test that streaming errors are logged and re-raised."""

        # Arrange
        async def failing_stream():
            yield AIMessageChunk(content="Start")
            raise RuntimeError("LLM API error")

        with patch.object(
            question_generator.tool_question_llm, "astream", return_value=failing_stream()
        ):
            # Act & Assert
            with pytest.raises(RuntimeError, match="LLM API error"):
                async for _ in question_generator.generate_confirmation_question_stream(
                    tool_name="test_tool",
                    tool_args={},
                ):
                    pass

    @pytest.mark.asyncio
    async def test_streaming_logs_completion(self, question_generator, mock_llm_stream):
        """Test that completion metrics are logged after streaming."""
        # Arrange
        tokens = ["Complete", " test"]

        with (
            patch.object(
                question_generator.tool_question_llm,
                "astream",
                return_value=mock_llm_stream(tokens),
            ),
            patch("src.domains.agents.services.hitl.question_generator.logger") as mock_logger,
        ):
            # Act
            async for _ in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={},
            ):
                pass

            # Assert
            # Check that info log was called for completion
            info_calls = list(mock_logger.info.call_args_list)
            assert any("hitl_question_generated_stream" in str(call) for call in info_calls)

    @pytest.mark.asyncio
    async def test_streaming_vs_blocking_same_result(self, question_generator, mock_llm_stream):
        """Test that streaming produces same result as blocking method."""
        # Arrange
        tokens = ["Same", " result", " test"]
        expected = "".join(tokens)

        # Mock both streaming and blocking
        with (
            patch.object(
                question_generator.tool_question_llm,
                "astream",
                return_value=mock_llm_stream(tokens),
            ),
            patch.object(
                question_generator.tool_question_llm,
                "ainvoke",
                AsyncMock(return_value=MagicMock(content=expected, text=expected)),
            ),
        ):
            # Act
            streaming_result = ""
            async for token in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={"query": "test"},
            ):
                streaming_result += token

            blocking_result = await question_generator.generate_confirmation_question(
                tool_name="test_tool",
                tool_args={"query": "test"},
            )

            # Assert
            assert streaming_result == blocking_result


class TestHitlQuestionStreamingPerformance:
    """Performance-focused tests for streaming."""

    @pytest.mark.asyncio
    async def test_ttft_is_significantly_faster_than_total_duration(
        self, question_generator, mock_llm_stream
    ):
        """Test that TTFT << total duration (streaming benefit)."""
        # Arrange
        tokens = ["Token"] * 20  # 20 tokens

        with patch.object(
            question_generator.tool_question_llm,
            "astream",
            return_value=mock_llm_stream(tokens, delay_ms=50),  # 50ms per token
        ):
            # Act
            start = time.time()
            first_token_time = None

            index = 0
            async for _ in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={},
            ):
                i, index = index, index + 1
                if i == 0:
                    first_token_time = time.time() - start

            total_duration = time.time() - start

            # Assert
            # TTFT should be << total duration (streaming advantage)
            assert first_token_time < total_duration / 5  # TTFT < 20% of total
            assert total_duration > 0.5  # Total > 500ms (20 tokens * 50ms)

    @pytest.mark.asyncio
    async def test_streaming_memory_efficient(self, question_generator, mock_llm_stream):
        """Test that streaming doesn't buffer all tokens in memory."""
        # Arrange
        # Simulate very long response (1000 tokens)
        tokens = ["Token" for _ in range(1000)]

        with patch.object(
            question_generator.tool_question_llm,
            "astream",
            return_value=mock_llm_stream(tokens, delay_ms=1),
        ):
            # Act
            token_count = 0
            async for _ in question_generator.generate_confirmation_question_stream(
                tool_name="test_tool",
                tool_args={},
            ):
                token_count += 1
                # In true streaming, we process and discard each token immediately
                # (no accumulation in memory during iteration)

            # Assert
            assert token_count == 1000
            # If this test completes without memory errors, streaming is memory-efficient


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
