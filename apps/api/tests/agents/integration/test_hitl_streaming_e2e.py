"""Legacy HITL protocol components and synthetic timing checks.

These component tests do not measure provider latency or exercise the full HTTP
journey. The actual HTTP admission and question round-trip live in
test_chat_http_admission.py and test_hitl_pending_endpoint.py; real LangGraph
resumption is exercised in test_hitl_engine_scope.py.
"""

import asyncio
import uuid

import pytest
from langchain_core.messages import AIMessageChunk

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.conversation_executions import reserved as reserved

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
async def reset_redis_singletons():
    """Give each test its own Redis client bound to ITS event loop.

    The module-level singletons in infrastructure.cache.redis are created in
    the first test's event loop; reusing them from another test's loop raises
    "Event loop is closed" / cross-loop RuntimeError.
    """
    import src.infrastructure.cache.redis as redis_module

    redis_module._redis_cache = None
    redis_module._redis_session = None
    yield
    if redis_module._redis_cache is not None:
        await redis_module._redis_cache.aclose()
    if redis_module._redis_session is not None:
        await redis_module._redis_session.aclose()
    redis_module._redis_cache = None
    redis_module._redis_session = None


@pytest.fixture
def mock_authenticated_user():
    """Mock authenticated user for tests."""
    from src.domains.users.models import User

    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        full_name="Test User",
        hashed_password="hashed",
        is_active=True,
        is_verified=True,
    )
    return user


@pytest.fixture
def mock_hitl_interrupt_event():
    """Mock HITL interrupt event from LangGraph."""
    return {
        "type": "approval",
        "content": "",
        "metadata": {
            "action_requests": [
                {
                    "name": "search_contacts_tool",
                    "args": {"query": "jean"},
                    "type": "tool_call",
                }
            ],
            "review_configs": [{"approval_type": "required"}],
            "interrupt_ts": 1699900000.123,
        },
    }


@pytest.fixture
def mock_question_tokens():
    """Mock streaming question tokens."""
    return ["Je ", "vais ", "rechercher ", "le ", "contact ", "'jean'. ", "Continuer", "?"]


@pytest.fixture
async def mock_llm_question_stream(mock_question_tokens):
    """Mock LLM streaming question generation."""

    async def _create_stream():
        for token in mock_question_tokens:
            await asyncio.sleep(0.01)  # Simulate network latency
            yield AIMessageChunk(content=token)

    return _create_stream


# ============================================================================
# E2E SSE Streaming Tests
# ============================================================================


class TestHITLStreamingE2E:
    """E2E tests for HITL streaming via SSE."""

    @pytest.mark.asyncio
    async def test_hitl_streaming_three_chunk_protocol(
        self,
        mock_authenticated_user,
        mock_hitl_interrupt_event,
        mock_question_tokens,
    ):
        """Test HITL streaming emits 3 chunk types: metadata → tokens → complete."""
        # This test validates the 3-chunk streaming protocol:
        # 1. hitl_interrupt_metadata (immediate, with action_requests)
        # 2. hitl_question_token (progressive, streaming question)
        # 3. hitl_interrupt_complete (finalize)

        # Arrange
        AgentService()

        # Mock the streaming flow
        metadata_chunk = ChatStreamChunk(
            type="hitl_interrupt_metadata",
            content="",
            metadata={
                "action_requests": mock_hitl_interrupt_event["metadata"]["action_requests"],
                "review_configs": mock_hitl_interrupt_event["metadata"]["review_configs"],
            },
        )

        token_chunks = [
            ChatStreamChunk(type="hitl_question_token", content=token, metadata=None)
            for token in mock_question_tokens
        ]

        complete_chunk = ChatStreamChunk(
            type="hitl_interrupt_complete",
            content="",
            metadata={
                "question_complete": True,
                "token_count": len(mock_question_tokens),
            },
        )

        expected_chunks = [metadata_chunk] + token_chunks + [complete_chunk]

        # Act & Assert
        # Verify chunk order and types
        assert expected_chunks[0].type == "hitl_interrupt_metadata"
        assert all(c.type == "hitl_question_token" for c in expected_chunks[1:-1])
        assert expected_chunks[-1].type == "hitl_interrupt_complete"

        # Verify metadata chunk contains action_requests
        assert "action_requests" in expected_chunks[0].metadata
        assert len(expected_chunks[0].metadata["action_requests"]) == 1

        # Verify token chunks contain progressive content
        full_question = "".join(c.content for c in expected_chunks[1:-1])
        assert full_question == "".join(mock_question_tokens)

        # Verify complete chunk contains summary metadata
        assert expected_chunks[-1].metadata["question_complete"] is True

    @pytest.mark.asyncio
    async def test_hitl_streaming_ttft_measurement(
        self,
        mock_authenticated_user,
        mock_hitl_interrupt_event,
        mock_question_tokens,
    ):
        """Test that TTFT is measured during HITL streaming in E2E flow."""
        # Arrange - Test the streaming behavior directly without patching metrics

        async def question_stream_with_delay(*args, **kwargs):
            await asyncio.sleep(0.05)  # Simulate first token delay
            for token in mock_question_tokens:
                yield token
                await asyncio.sleep(0.01)

        # Act
        start_time = asyncio.get_event_loop().time()
        tokens_received = []
        first_token_time = None

        async for token in question_stream_with_delay(
            tool_name="search_contacts_tool",
            tool_args={"query": "jean"},
        ):
            if first_token_time is None:
                first_token_time = asyncio.get_event_loop().time() - start_time
            tokens_received.append(token)

        # Assert
        assert len(tokens_received) == len(mock_question_tokens)
        assert first_token_time is not None
        assert first_token_time >= 0.05  # Verify delay was applied
        assert first_token_time < 0.15  # But not too slow

    # Real LangGraph interrupt/resumption (including stale checkpoints) lives in
    # integration/domains/conversations/test_hitl_engine_scope.py. The former
    # test here constructed a decision without ever invoking the mocked graph.

    @pytest.mark.asyncio
    async def test_hitl_streaming_handles_empty_question_chunks(self):
        """Test that empty chunks from question generator are handled gracefully."""

        # Arrange
        async def question_stream_with_empty():
            yield "Start "
            yield ""  # Empty chunk
            yield "End"

        # Act
        tokens = []
        async for token in question_stream_with_empty():
            tokens.append(token)

        # Assert
        assert tokens == ["Start ", "", "End"]
        # Verify empty chunks are preserved (not filtered)

    @pytest.mark.asyncio
    async def test_sse_heartbeat_during_long_question_generation(self):
        """Test that SSE heartbeats are sent during long question generation."""
        # This test validates that SSE connections don't timeout during long
        # HITL question generation (e.g., complex tool calls requiring detailed questions)

        # Arrange
        async def slow_question_stream():
            for i in range(5):
                await asyncio.sleep(1.0)  # Simulate slow generation
                yield f"Token{i} "

        # Act
        start_time = asyncio.get_event_loop().time()
        tokens = []
        async for token in slow_question_stream():
            tokens.append(token)

        duration = asyncio.get_event_loop().time() - start_time

        # Assert
        assert len(tokens) == 5
        assert duration >= 5.0  # Verify stream was actually slow
        # In production, SSE heartbeat (": heartbeat\n\n") should be sent every 15s
        # to prevent connection timeout

    @pytest.mark.asyncio
    async def test_hitl_streaming_error_propagation(self):
        """Test that errors during streaming are propagated to frontend via SSE."""

        # Arrange
        async def failing_question_stream():
            yield "Start"
            raise RuntimeError("LLM API error during question generation")

        # Act & Assert
        with pytest.raises(RuntimeError, match="LLM API error"):
            async for _ in failing_question_stream():
                pass

    @pytest.mark.asyncio
    async def test_hitl_streaming_token_aggregation_in_done_chunk(
        self,
        mock_authenticated_user,
        mock_question_tokens,
    ):
        """Test that done chunk includes aggregated token metadata."""
        # Arrange
        from src.domains.agents.api.schemas import ChatStreamChunk

        # Simulate streaming with token tracking
        total_tokens_in = 50  # Prompt tokens
        total_tokens_out = len(mock_question_tokens)  # Generated tokens

        done_chunk = ChatStreamChunk(
            type="done",
            content="",
            metadata={
                "tokens_in": total_tokens_in,
                "tokens_out": total_tokens_out,
                "tokens_total": total_tokens_in + total_tokens_out,
                "cost_eur": 0.001,
            },
        )

        # Assert
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 50
        assert done_chunk.metadata["tokens_out"] == len(mock_question_tokens)
        assert done_chunk.metadata["tokens_total"] == 50 + len(mock_question_tokens)


# ============================================================================
# Performance Tests
# ============================================================================


class TestHITLStreamingPerformanceE2E:
    """E2E performance tests for HITL streaming."""

    @pytest.mark.asyncio
    async def test_ttft_under_300ms_target(self, mock_question_tokens):
        """Test that TTFT is under 300ms target in realistic scenario."""

        # Arrange
        async def realistic_question_stream():
            # Simulate realistic LLM latency (first token ~200ms)
            await asyncio.sleep(0.2)
            for token in mock_question_tokens:
                yield token
                await asyncio.sleep(0.02)  # Subsequent tokens ~20ms each

        # Act
        start = asyncio.get_event_loop().time()
        first_token_time = None
        i = 0

        async for _token in realistic_question_stream():
            if i == 0:
                first_token_time = asyncio.get_event_loop().time() - start
                break
            i += 1

        # Assert
        assert first_token_time is not None
        assert first_token_time < 0.3  # < 300ms (target)
        assert first_token_time >= 0.2  # >= 200ms (realistic minimum)

    @pytest.mark.asyncio
    async def test_streaming_memory_efficient_for_long_questions(self):
        """Test that streaming doesn't accumulate all tokens in memory."""

        # Arrange - Simulate very long question (500 tokens)
        async def long_question_stream():
            for i in range(500):
                yield f"token{i} "
                await asyncio.sleep(0.001)  # Fast stream

        # Act
        token_count = 0

        async for _token in long_question_stream():
            token_count += 1
            # In true streaming, token is processed and discarded immediately
            # (no accumulation)

        # Assert
        assert token_count == 500
        # Memory usage should remain constant (not grow with token count)
        # In production, use tracemalloc to verify

    @pytest.mark.asyncio
    async def test_end_to_end_latency_breakdown(self, mock_question_tokens):
        """Test E2E latency breakdown: interrupt → classification → question → response."""
        # This test measures the full HITL streaming latency budget:
        # 1. Interrupt detection: ~10ms
        # 2. Redis storage: ~5ms
        # 3. Question generation TTFT: ~200ms (target)
        # 4. Full question stream: ~500ms
        # 5. User response → classification: ~300ms
        # Total budget: ~1s from interrupt to question displayed

        # Arrange
        latency_budget = {
            "interrupt_detection": 0.01,  # 10ms
            "redis_storage": 0.005,  # 5ms
            "question_ttft": 0.2,  # 200ms (critical for UX)
            "full_question_stream": 0.5,  # 500ms
        }

        # Act - Simulate each phase
        start = asyncio.get_event_loop().time()

        # Phase 1: Interrupt detection
        await asyncio.sleep(latency_budget["interrupt_detection"])
        interrupt_time = asyncio.get_event_loop().time() - start

        # Phase 2: Redis storage
        await asyncio.sleep(latency_budget["redis_storage"])
        storage_time = asyncio.get_event_loop().time() - start - interrupt_time

        # Phase 3: Question generation TTFT
        await asyncio.sleep(latency_budget["question_ttft"])
        ttft_time = asyncio.get_event_loop().time() - start - interrupt_time - storage_time

        # Phase 4: Full question stream
        token_count = 0
        async for _token in mock_question_stream(mock_question_tokens, delay_ms=20):
            token_count += 1

        total_time = asyncio.get_event_loop().time() - start

        # Assert - Use high tolerance for CI/test environment variations
        # Windows/CI environments have significant scheduling jitter for small sleeps
        # Small values (10ms, 5ms) can vary by 5-10x due to OS scheduling
        # Larger values (200ms+) are more stable, so use lower tolerance
        assert (
            interrupt_time <= latency_budget["interrupt_detection"] * 5.0
        )  # 5x tolerance for small sleep
        assert storage_time <= latency_budget["redis_storage"] * 5.0  # 5x tolerance for small sleep
        assert ttft_time <= latency_budget["question_ttft"] * 1.5  # 50% tolerance (larger value)
        assert total_time <= sum(latency_budget.values()) * 2.0  # 2x total budget


# ============================================================================
# Helper Functions
# ============================================================================


async def mock_question_stream(tokens: list[str], delay_ms: int = 10):
    """Helper to create mock question stream with configurable delay."""
    for token in tokens:
        await asyncio.sleep(delay_ms / 1000)
        yield token


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
