"""
Unit tests for LLM Instrumentation utilities (Phase 3.1.5 + 3.1.6.3).

Tests:
- create_instrumented_config() metadata enrichment
- Subgraph tracing metadata (parent_trace_id, subgraph_name, depth)
- Prometheus metrics instrumentation (Phase 3.1.6.3)
- Base config merging
- Graceful degradation (Langfuse disabled)

Coverage Target: 80%+

Note: This tests metadata logic and Prometheus metrics, not full callback integration
(callback logic is tested separately in test_callback_factory.py).
"""

from unittest.mock import Mock, patch

import pytest

from src.infrastructure.llm.instrumentation import create_instrumented_config

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_callback_factory_disabled():
    """Mock callback factory that is disabled."""
    factory = Mock()
    factory.is_enabled.return_value = False
    return factory


@pytest.fixture
def mock_callback_factory_enabled():
    """Mock callback factory that is enabled."""
    factory = Mock()
    factory.is_enabled.return_value = True
    factory.create_callbacks.return_value = []  # Return empty list for simplicity
    return factory


# ============================================================================
# TEST METADATA ENRICHMENT
# ============================================================================


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_basic_metadata(
    mock_get_factory, mock_callback_factory_disabled
):
    """Test basic metadata enrichment without Langfuse callbacks."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="router",
        session_id="session-123",
        user_id="user-456",
    )

    # Verify metadata exists
    assert "metadata" in config
    metadata = config["metadata"]

    # Verify basic metadata
    assert metadata["llm_type"] == "router"
    assert metadata["instrumentation_version"] == "1.0.0"

    # Verify Langfuse context keys
    assert metadata["langfuse_session_id"] == "session-123"
    assert metadata["langfuse_user_id"] == "user-456"
    assert metadata["langfuse_trace_name"] == "router_call"  # Default
    assert metadata["langfuse_tags"] == ["router"]  # Auto-added
    assert metadata["langfuse_trace_depth"] == 0  # Default


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_custom_metadata(
    mock_get_factory, mock_callback_factory_disabled
):
    """Test custom metadata merge."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="planner",
        metadata={"custom_key": "custom_value", "request_id": "req-789"},
    )

    metadata = config["metadata"]

    # Verify custom metadata is merged
    assert metadata["custom_key"] == "custom_value"
    assert metadata["request_id"] == "req-789"

    # Verify base metadata still present
    assert metadata["llm_type"] == "planner"
    assert metadata["instrumentation_version"] == "1.0.0"


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_custom_trace_name(
    mock_get_factory, mock_callback_factory_disabled
):
    """Test custom trace name override."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="contacts_agent",
        trace_name="custom_trace_name",
    )

    metadata = config["metadata"]
    assert metadata["langfuse_trace_name"] == "custom_trace_name"


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_custom_tags(mock_get_factory, mock_callback_factory_disabled):
    """Test custom tags."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="emails_agent",
        tags=["tag1", "tag2"],
    )

    metadata = config["metadata"]
    # llm_type auto-added + custom tags
    assert metadata["langfuse_tags"] == ["emails_agent", "tag1", "tag2"]


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_trace_id(mock_get_factory, mock_callback_factory_disabled):
    """Test trace_id for distributed tracing."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="router",
        trace_id="trace-abc-123",
    )

    metadata = config["metadata"]
    assert metadata["langfuse_trace_id"] == "trace-abc-123"


# ============================================================================
# TEST SUBGRAPH TRACING METADATA (Phase 3.1.5)
# ============================================================================


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_root_level(mock_get_factory, mock_callback_factory_disabled):
    """Test metadata at root level (depth=0, no parent)."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="orchestrator",
        session_id="session-123",
        depth=0,
    )

    metadata = config["metadata"]

    # Root level: depth=0, no parent
    assert metadata["langfuse_trace_depth"] == 0
    assert "langfuse_parent_trace_id" not in metadata
    assert "langfuse_subgraph_name" not in metadata


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_subgraph_level(
    mock_get_factory, mock_callback_factory_disabled
):
    """Test metadata at subgraph level (depth=1, with parent)."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="contacts_agent",
        session_id="session-123",
        parent_trace_id="trace-parent-abc",
        subgraph_name="contacts_subgraph",
        depth=1,
    )

    metadata = config["metadata"]

    # Subgraph level: depth=1, parent + subgraph_name
    assert metadata["langfuse_trace_depth"] == 1
    assert metadata["langfuse_parent_trace_id"] == "trace-parent-abc"
    assert metadata["langfuse_subgraph_name"] == "contacts_subgraph"


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_nested_level(mock_get_factory, mock_callback_factory_disabled):
    """Test metadata at nested level (depth=2+)."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="nested_agent",
        session_id="session-123",
        parent_trace_id="trace-parent-xyz",
        subgraph_name="nested_subgraph",
        depth=2,
    )

    metadata = config["metadata"]

    # Nested level: depth=2
    assert metadata["langfuse_trace_depth"] == 2
    assert metadata["langfuse_parent_trace_id"] == "trace-parent-xyz"
    assert metadata["langfuse_subgraph_name"] == "nested_subgraph"


# ============================================================================
# TEST PROMETHEUS METRICS INSTRUMENTATION (Phase 3.1.6.3)
# ============================================================================


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
@patch("src.infrastructure.observability.metrics_langfuse.langfuse_trace_depth")
@patch("src.infrastructure.observability.metrics_langfuse.langfuse_subgraph_invocations")
def test_create_instrumented_config_prometheus_metrics_root(
    mock_subgraph_metric, mock_depth_metric, mock_get_factory, mock_callback_factory_disabled
):
    """Test Prometheus metrics at root level (depth=0, no subgraph_name)."""
    mock_get_factory.return_value = mock_callback_factory_disabled
    mock_depth_metric.labels.return_value.observe = Mock()
    mock_subgraph_metric.labels.return_value.inc = Mock()

    create_instrumented_config(
        llm_type="router",
        session_id="session-123",
        depth=0,
    )

    # Verify trace_depth metric called
    mock_depth_metric.labels.assert_called_once_with(depth_level="0")
    mock_depth_metric.labels.return_value.observe.assert_called_once_with(0)

    # Verify subgraph_invocations NOT called (no subgraph_name)
    mock_subgraph_metric.labels.assert_not_called()


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
@patch("src.infrastructure.observability.metrics_langfuse.langfuse_trace_depth")
@patch("src.infrastructure.observability.metrics_langfuse.langfuse_subgraph_invocations")
def test_create_instrumented_config_prometheus_metrics_subgraph(
    mock_subgraph_metric, mock_depth_metric, mock_get_factory, mock_callback_factory_disabled
):
    """Test Prometheus metrics at subgraph level (depth=1, with subgraph_name)."""
    mock_get_factory.return_value = mock_callback_factory_disabled
    mock_depth_metric.labels.return_value.observe = Mock()
    mock_subgraph_metric.labels.return_value.inc = Mock()

    create_instrumented_config(
        llm_type="contacts_agent",
        session_id="session-123",
        parent_trace_id="trace-parent-123",
        subgraph_name="contacts_subgraph",
        depth=1,
    )

    # Verify trace_depth metric called
    mock_depth_metric.labels.assert_called_once_with(depth_level="1")
    mock_depth_metric.labels.return_value.observe.assert_called_once_with(1)

    # Verify subgraph_invocations called
    mock_subgraph_metric.labels.assert_called_once_with(
        subgraph_name="contacts_subgraph",
        status="invoked",
    )
    mock_subgraph_metric.labels.return_value.inc.assert_called_once()


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
@patch("src.infrastructure.observability.metrics_langfuse.langfuse_trace_depth")
@patch("src.infrastructure.observability.metrics_langfuse.langfuse_subgraph_invocations")
def test_create_instrumented_config_prometheus_metrics_nested(
    mock_subgraph_metric, mock_depth_metric, mock_get_factory, mock_callback_factory_disabled
):
    """Test Prometheus metrics at nested level (depth=2+)."""
    mock_get_factory.return_value = mock_callback_factory_disabled
    mock_depth_metric.labels.return_value.observe = Mock()
    mock_subgraph_metric.labels.return_value.inc = Mock()

    create_instrumented_config(
        llm_type="nested_agent",
        session_id="session-123",
        parent_trace_id="trace-parent-456",
        subgraph_name="nested_subgraph",
        depth=3,
    )

    # Verify trace_depth metric called with depth=3
    mock_depth_metric.labels.assert_called_once_with(depth_level="3")
    mock_depth_metric.labels.return_value.observe.assert_called_once_with(3)

    # Verify subgraph_invocations called
    mock_subgraph_metric.labels.assert_called_once_with(
        subgraph_name="nested_subgraph",
        status="invoked",
    )


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
@patch(
    "src.infrastructure.observability.metrics_langfuse.langfuse_trace_depth",
    side_effect=Exception("Metrics failed"),
)
def test_create_instrumented_config_prometheus_metrics_graceful_degradation(
    mock_depth_metric, mock_get_factory, mock_callback_factory_disabled
):
    """Test graceful degradation when Prometheus metrics fail."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    # Should not raise exception even if metrics fail
    config = create_instrumented_config(
        llm_type="router",
        session_id="session-123",
        depth=0,
    )

    # Config should still be created
    assert "metadata" in config
    assert config["metadata"]["llm_type"] == "router"


# ============================================================================
# TEST BASE CONFIG MERGING
# ============================================================================


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_base_config_merge(
    mock_get_factory, mock_callback_factory_disabled
):
    """Test merging with existing base config."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    base_config = {
        "recursion_limit": 50,
        "max_concurrency": 10,
        "custom_key": "base_value",
    }

    config = create_instrumented_config(
        llm_type="planner",
        session_id="session-123",
        base_config=base_config,
    )

    # Verify base config preserved
    assert config["recursion_limit"] == 50
    assert config["max_concurrency"] == 10
    assert config["custom_key"] == "base_value"

    # Verify metadata added
    assert "metadata" in config
    assert config["metadata"]["llm_type"] == "planner"


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_no_base_config(
    mock_get_factory, mock_callback_factory_disabled
):
    """Test creation without base config."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="router",
        session_id="session-123",
    )

    # Should only have metadata (no other keys)
    assert "metadata" in config
    # May have callbacks if factory enabled, but in this test factory is disabled
    assert len(config) >= 1  # At least metadata


# ============================================================================
# TEST CALLBACK FACTORY INTEGRATION
# ============================================================================


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_factory_disabled(
    mock_get_factory, mock_callback_factory_disabled
):
    """Test behavior when callback factory is disabled."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(
        llm_type="router",
        session_id="session-123",
    )

    # Verify metadata still created (even if Langfuse disabled)
    assert "metadata" in config
    assert config["metadata"]["llm_type"] == "router"

    # Verify callbacks NOT created (factory disabled)
    assert "callbacks" not in config


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_factory_none(mock_get_factory):
    """Test behavior when callback factory is None."""
    mock_get_factory.return_value = None

    config = create_instrumented_config(
        llm_type="router",
        session_id="session-123",
    )

    # Metadata should still be created
    assert "metadata" in config
    assert config["metadata"]["llm_type"] == "router"


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_factory_enabled(
    mock_get_factory, mock_callback_factory_enabled
):
    """Test behavior when callback factory is enabled."""
    mock_get_factory.return_value = mock_callback_factory_enabled

    config = create_instrumented_config(
        llm_type="router",
        session_id="session-123",
    )

    # Verify callbacks created
    mock_callback_factory_enabled.create_callbacks.assert_called_once()

    # Verify metadata created
    assert "metadata" in config
    assert config["metadata"]["llm_type"] == "router"


# ============================================================================
# TEST MINIMAL CONFIG (ALL OPTIONAL PARAMS)
# ============================================================================


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
def test_create_instrumented_config_minimal(mock_get_factory, mock_callback_factory_disabled):
    """Test minimal config with only llm_type."""
    mock_get_factory.return_value = mock_callback_factory_disabled

    config = create_instrumented_config(llm_type="router")

    # Verify metadata created with defaults
    assert "metadata" in config
    metadata = config["metadata"]

    assert metadata["llm_type"] == "router"
    assert metadata["instrumentation_version"] == "1.0.0"
    assert metadata["langfuse_trace_name"] == "router_call"  # Default
    assert metadata["langfuse_tags"] == ["router"]  # Auto-added
    assert metadata["langfuse_trace_depth"] == 0  # Default

    # Optional params not present
    assert "langfuse_session_id" not in metadata
    assert "langfuse_user_id" not in metadata
    assert "langfuse_trace_id" not in metadata
    assert "langfuse_parent_trace_id" not in metadata
    assert "langfuse_subgraph_name" not in metadata


# ============================================================================
# TEST DEPTH LEVELS VARIETY
# ============================================================================


@patch("src.infrastructure.llm.instrumentation.get_callback_factory")
@patch("src.infrastructure.observability.metrics_langfuse.langfuse_trace_depth")
def test_create_instrumented_config_various_depth_levels(
    mock_depth_metric, mock_get_factory, mock_callback_factory_disabled
):
    """Test various depth levels (0, 1, 2, 3, 4, 5)."""
    mock_get_factory.return_value = mock_callback_factory_disabled
    mock_depth_metric.labels.return_value.observe = Mock()

    # Test depth 0
    create_instrumented_config(llm_type="router", depth=0)
    assert mock_depth_metric.labels.call_args_list[-1][1]["depth_level"] == "0"

    # Test depth 1
    create_instrumented_config(llm_type="agent", depth=1)
    assert mock_depth_metric.labels.call_args_list[-1][1]["depth_level"] == "1"

    # Test depth 2
    create_instrumented_config(llm_type="agent", depth=2)
    assert mock_depth_metric.labels.call_args_list[-1][1]["depth_level"] == "2"

    # Test depth 5 (edge case)
    create_instrumented_config(llm_type="agent", depth=5)
    assert mock_depth_metric.labels.call_args_list[-1][1]["depth_level"] == "5"

    # Verify observe called with correct values
    observe_calls = mock_depth_metric.labels.return_value.observe.call_args_list
    assert observe_calls[-4][0][0] == 0
    assert observe_calls[-3][0][0] == 1
    assert observe_calls[-2][0][0] == 2
    assert observe_calls[-1][0][0] == 5
