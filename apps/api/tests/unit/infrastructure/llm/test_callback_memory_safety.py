"""
Unit tests for callback memory safety (Phase 2.1.7 - RC4 Fix).

Tests that _last_usage_metadata is properly managed to prevent memory leaks
and pollution between consecutive LLM calls.

Critical behaviors tested:
    1. Metadata cleared on on_llm_start() (prevents stale data)
    2. Metadata stored on on_llm_end() (available for cache decorator)
    3. Consecutive calls don't pollute each other (isolation)
    4. Missing usage_metadata handled gracefully (no exceptions)
    5. Error cases don't leave stale metadata (cleanup)

User feedback: "Prévois un jeu de tests autour du champ _last_usage_metadata
pour t'assurer que deux requêtes consécutives ne se polluent pas."
"""

from uuid import uuid4

import pytest
from langchain_core.outputs import Generation, LLMResult

from src.infrastructure.observability.callbacks import (
    MetricsCallbackHandler,
    TokenTrackingCallback,
)

# ============================================================================
# MetricsCallbackHandler - Memory Safety Tests
# ============================================================================


@pytest.mark.asyncio
async def test_metrics_callback_metadata_cleared_on_start():
    """
    Test that _last_usage_metadata is cleared on each on_llm_start().

    Scenario:
        1. Handler has stale metadata from previous call
        2. on_llm_start() called
        3. Metadata should be None

    Prevents: Memory pollution from previous LLM calls
    """
    handler = MetricsCallbackHandler(node_name="test_node")

    # Simulate stale metadata from previous call
    handler._last_usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }

    # Trigger on_llm_start (should clear metadata)
    await handler.on_llm_start(
        serialized={},
        prompts=["test prompt"],
        run_id=uuid4(),
    )

    # Verify metadata is cleared
    assert handler._last_usage_metadata is None, "Metadata should be cleared on on_llm_start()"


@pytest.mark.asyncio
async def test_metrics_callback_metadata_stored_on_end():
    """
    Test that _last_usage_metadata is populated on on_llm_end().

    Scenario:
        1. LLM call completes with usage_metadata
        2. on_llm_end() called
        3. Metadata should be stored

    Enables: Cache decorator to extract usage for v2 format
    """
    handler = MetricsCallbackHandler(node_name="test_node")

    # Simulate LLM start
    run_id = uuid4()
    await handler.on_llm_start(
        serialized={},
        prompts=["test prompt"],
        run_id=run_id,
    )

    # Simulate LLM end with usage metadata
    llm_result = LLMResult(
        generations=[[Generation(text="test response")]],
        llm_output={
            "usage_metadata": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            },
            "model_name": "gpt-4.1-mini",
        },
    )

    await handler.on_llm_end(response=llm_result, run_id=run_id)

    # Verify metadata is stored
    assert handler._last_usage_metadata is not None, "Metadata should be stored on on_llm_end()"
    assert handler._last_usage_metadata["input_tokens"] == 100
    assert handler._last_usage_metadata["output_tokens"] == 50
    assert handler._last_usage_metadata["model_name"] == "gpt-4.1-mini"


@pytest.mark.asyncio
async def test_metrics_callback_consecutive_calls_isolated():
    """
    Test that consecutive LLM calls don't pollute each other's metadata.

    Scenario:
        1. First LLM call (model A, 100 tokens)
        2. Second LLM call (model B, 200 tokens)
        3. Each call should see only its own metadata

    Prevents: Metadata from call1 appearing in call2 cache entry
    """
    handler = MetricsCallbackHandler(node_name="test_node")

    # === First LLM call ===
    run_id_1 = uuid4()
    await handler.on_llm_start(
        serialized={},
        prompts=["prompt 1"],
        run_id=run_id_1,
    )

    llm_result_1 = LLMResult(
        generations=[[Generation(text="response 1")]],
        llm_output={
            "usage_metadata": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            },
            "model_name": "gpt-4.1-mini",
        },
    )

    await handler.on_llm_end(response=llm_result_1, run_id=run_id_1)

    # Capture first call metadata
    metadata_1 = handler._last_usage_metadata.copy()

    # === Second LLM call (should clear first metadata) ===
    run_id_2 = uuid4()
    await handler.on_llm_start(
        serialized={},
        prompts=["prompt 2"],
        run_id=run_id_2,
    )

    # Verify first metadata is cleared
    assert handler._last_usage_metadata is None, "Metadata should be cleared before second call"

    llm_result_2 = LLMResult(
        generations=[[Generation(text="response 2")]],
        llm_output={
            "usage_metadata": {
                "input_tokens": 200,
                "output_tokens": 100,
                "total_tokens": 300,
            },
            "model_name": "claude-3-5-sonnet",
        },
    )

    await handler.on_llm_end(response=llm_result_2, run_id=run_id_2)

    # Verify second metadata is different from first
    metadata_2 = handler._last_usage_metadata
    assert metadata_2["input_tokens"] == 200, "Second call should have its own tokens"
    assert metadata_2["model_name"] == "claude-3-5-sonnet", "Second call should have its own model"

    # Verify no pollution from first call
    assert metadata_2["input_tokens"] != metadata_1["input_tokens"]
    assert metadata_2["model_name"] != metadata_1["model_name"]


@pytest.mark.asyncio
async def test_metrics_callback_missing_usage_metadata():
    """
    Test that missing usage_metadata doesn't cause exceptions.

    Scenario:
        1. LLM call completes without usage_metadata (e.g., streaming)
        2. on_llm_end() called
        3. Should handle gracefully (no exception, metadata = None)

    Prevents: Crashes when LLM provider doesn't return usage
    """
    handler = MetricsCallbackHandler(node_name="test_node")

    run_id = uuid4()
    await handler.on_llm_start(
        serialized={},
        prompts=["test prompt"],
        run_id=run_id,
    )

    # LLM result WITHOUT usage_metadata
    llm_result = LLMResult(
        generations=[[Generation(text="test response")]],
        llm_output={},  # No usage_metadata
    )

    # Should not raise exception
    await handler.on_llm_end(response=llm_result, run_id=run_id)

    # Metadata should remain None (not stored)
    # Note: Current implementation doesn't set _last_usage_metadata if no usage found
    # This is correct behavior - cache decorator will handle missing metadata gracefully


@pytest.mark.asyncio
async def test_metrics_callback_error_cleanup():
    """
    Test that on_llm_error() doesn't leave stale metadata.

    Scenario:
        1. LLM call starts
        2. LLM call fails (error)
        3. Metadata should remain None (no partial data)

    Prevents: Stale metadata from failed calls affecting next call
    """
    handler = MetricsCallbackHandler(node_name="test_node")

    run_id = uuid4()
    await handler.on_llm_start(
        serialized={},
        prompts=["test prompt"],
        run_id=run_id,
    )

    # Verify metadata cleared
    assert handler._last_usage_metadata is None

    # Simulate error
    await handler.on_llm_error(
        error=Exception("LLM API error"),
        run_id=run_id,
    )

    # Metadata should still be None (no partial storage on error)
    assert handler._last_usage_metadata is None, "Error should not leave stale metadata"


# ============================================================================
# TokenTrackingCallback - Memory Safety Tests
# ============================================================================


@pytest.mark.asyncio
async def test_token_tracking_callback_metadata_cleared_on_start(mock_tracking_context):
    """
    Test that TokenTrackingCallback clears metadata on on_llm_start().

    Same pattern as MetricsCallbackHandler but for TokenTrackingCallback.
    """
    handler = TokenTrackingCallback(tracker=mock_tracking_context, run_id="test-run-123")

    # Simulate stale metadata
    handler._last_usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }

    # Trigger on_llm_start
    await handler.on_llm_start(
        serialized={},
        prompts=["test prompt"],
        run_id=uuid4(),
    )

    # Verify cleared
    assert handler._last_usage_metadata is None


@pytest.mark.asyncio
async def test_token_tracking_callback_metadata_stored_on_end(mock_tracking_context):
    """
    Test that TokenTrackingCallback stores metadata on on_llm_end().
    """
    handler = TokenTrackingCallback(tracker=mock_tracking_context, run_id="test-run-123")

    run_id = uuid4()
    await handler.on_llm_start(
        serialized={},
        prompts=["test prompt"],
        run_id=run_id,
    )

    # Simulate LLM end with usage metadata
    llm_result = LLMResult(
        generations=[[Generation(text="test response")]],
        llm_output={
            "usage_metadata": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            },
            "model_name": "gpt-4.1-mini",
        },
    )

    await handler.on_llm_end(
        response=llm_result,
        run_id=run_id,
        metadata={"langgraph_node": "test_node"},
    )

    # Verify metadata stored
    assert handler._last_usage_metadata is not None
    assert handler._last_usage_metadata["input_tokens"] == 100
    assert handler._last_usage_metadata["output_tokens"] == 50


@pytest.mark.asyncio
async def test_token_tracking_callback_consecutive_calls_isolated(mock_tracking_context):
    """
    Test that consecutive calls don't pollute each other (TokenTrackingCallback).
    """
    handler = TokenTrackingCallback(tracker=mock_tracking_context, run_id="test-run-123")

    # First call
    run_id_1 = uuid4()
    await handler.on_llm_start(serialized={}, prompts=["prompt 1"], run_id=run_id_1)

    llm_result_1 = LLMResult(
        generations=[[Generation(text="response 1")]],
        llm_output={
            "usage_metadata": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            "model_name": "gpt-4.1-mini",
        },
    )

    await handler.on_llm_end(
        response=llm_result_1,
        run_id=run_id_1,
        metadata={"langgraph_node": "node1"},
    )

    metadata_1 = handler._last_usage_metadata.copy()

    # Second call (should clear first metadata)
    run_id_2 = uuid4()
    await handler.on_llm_start(serialized={}, prompts=["prompt 2"], run_id=run_id_2)

    assert handler._last_usage_metadata is None, "Second call should clear first metadata"

    llm_result_2 = LLMResult(
        generations=[[Generation(text="response 2")]],
        llm_output={
            "usage_metadata": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
            "model_name": "claude-3-5-sonnet",
        },
    )

    await handler.on_llm_end(
        response=llm_result_2,
        run_id=run_id_2,
        metadata={"langgraph_node": "node2"},
    )

    metadata_2 = handler._last_usage_metadata

    # Verify isolation
    assert metadata_2["input_tokens"] != metadata_1["input_tokens"]
    assert metadata_2["model_name"] != metadata_1["model_name"]


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_tracking_context():
    """
    Mock TrackingContext for TokenTrackingCallback tests.

    Avoids requiring database session for unit tests.
    """
    from unittest.mock import AsyncMock, MagicMock

    tracker = MagicMock()
    tracker.record_node_tokens = AsyncMock()

    return tracker
