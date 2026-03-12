"""
Integration tests for invoke_helpers with callbacks.

Tests the complete flow of metadata propagation from config enrichment
to callback invocation, verifying that node_name is correctly received
by callbacks for token tracking.

Phase: 2.1 - Token Tracking Alignment Fix
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.infrastructure.llm.invoke_helpers import (
    create_instrumented_config_from_node,
    enrich_config_with_node_metadata,
)


class TestMetadataPropagationToCallbacks:
    """Test that enriched metadata reaches callbacks correctly."""

    @pytest.mark.asyncio
    async def test_callback_receives_node_name_from_enriched_config(self):
        """Test that callbacks receive node_name via kwargs['metadata']."""
        # Create a mock callback that captures kwargs
        mock_callback = AsyncMock()
        captured_kwargs = {}

        async def capture_on_llm_end(response, **kwargs):
            """Capture kwargs passed to on_llm_end."""
            captured_kwargs.update(kwargs)

        mock_callback.on_llm_end = capture_on_llm_end

        # Create enriched config
        config = enrich_config_with_node_metadata(None, "router")
        config["callbacks"] = [mock_callback]

        # Simulate LLM invocation with enriched config
        # In real scenario, this would be llm.ainvoke(messages, config=config)
        # For testing, we manually call the callback as LLM would
        response = AIMessage(content="test response")
        await mock_callback.on_llm_end(response, **config.get("metadata", {}))

        # Verify callback received node_name
        assert "langgraph_node" in captured_kwargs
        assert captured_kwargs["langgraph_node"] == "router"

    def test_create_instrumented_config_from_node_includes_node_metadata(self):
        """Test that create_instrumented_config_from_node enriches metadata."""
        # Create config without node metadata
        base_config: RunnableConfig = {
            "configurable": {"thread_id": "test_session"},
        }

        # Create instrumented config
        result = create_instrumented_config_from_node(
            llm_type="planner",
            state={"session_id": "test_session", "user_id": 123},
            base_config=base_config,
        )

        # Verify node_name in metadata
        assert "metadata" in result
        assert result["metadata"]["langgraph_node"] == "planner"

    def test_create_instrumented_config_from_node_extracts_from_base_config(self):
        """Test extraction of node_name from base_config (LangGraph pattern)."""
        # Simulate config from LangGraph with langgraph_node already set
        base_config: RunnableConfig = {
            "metadata": {
                "langgraph_node": "contacts_agent",
                "run_id": "test_run_123",
            }
        }

        # Create instrumented config
        result = create_instrumented_config_from_node(
            llm_type="contacts",  # Different from node name in config
            base_config=base_config,
        )

        # Verify node_name extracted from base_config (takes precedence)
        assert result["metadata"]["langgraph_node"] == "contacts_agent"

    def test_create_instrumented_config_from_node_fallback_to_llm_type(self):
        """Test fallback to llm_type when no node_name in base_config."""
        # Config without langgraph_node
        base_config: RunnableConfig = {"metadata": {"custom_field": "custom_value"}}

        # Create instrumented config
        result = create_instrumented_config_from_node(
            llm_type="response",
            base_config=base_config,
        )

        # Verify fallback to llm_type
        assert result["metadata"]["langgraph_node"] == "response"
        # Note: create_instrumented_config_from_node may not preserve all metadata
        # from base_config depending on implementation. Check if langgraph_node is set correctly.

    @pytest.mark.asyncio
    async def test_multiple_callbacks_all_receive_node_name(self):
        """Test that multiple callbacks all receive enriched metadata."""
        # Create multiple mock callbacks
        mock_callback1 = AsyncMock()
        mock_callback2 = AsyncMock()
        mock_callback3 = AsyncMock()

        captured_kwargs_1 = {}
        captured_kwargs_2 = {}
        captured_kwargs_3 = {}

        async def capture_1(response, **kwargs):
            captured_kwargs_1.update(kwargs)

        async def capture_2(response, **kwargs):
            captured_kwargs_2.update(kwargs)

        async def capture_3(response, **kwargs):
            captured_kwargs_3.update(kwargs)

        mock_callback1.on_llm_end = capture_1
        mock_callback2.on_llm_end = capture_2
        mock_callback3.on_llm_end = capture_3

        # Create enriched config with multiple callbacks
        config = enrich_config_with_node_metadata(None, "planner")
        config["callbacks"] = [mock_callback1, mock_callback2, mock_callback3]

        # Simulate LLM calling all callbacks
        response = AIMessage(content="test response")
        for callback in config["callbacks"]:
            await callback.on_llm_end(response, **config.get("metadata", {}))

        # Verify all callbacks received node_name
        assert captured_kwargs_1["langgraph_node"] == "planner"
        assert captured_kwargs_2["langgraph_node"] == "planner"
        assert captured_kwargs_3["langgraph_node"] == "planner"

    def test_enrichment_preserves_callback_list(self):
        """Test that enrichment doesn't modify callback list."""
        # Config with existing callbacks
        existing_callback = MagicMock()
        config: RunnableConfig = {
            "callbacks": [existing_callback],
            "metadata": {"existing": "metadata"},
        }

        # Enrich config
        result = enrich_config_with_node_metadata(config, "router")

        # Verify original callback preserved + possible MetricsCallback added
        assert existing_callback in result["callbacks"]
        assert len(result["callbacks"]) >= 1  # At least original callback
        # Metadata enriched
        assert result["metadata"]["langgraph_node"] == "router"
        assert result["metadata"]["existing"] == "metadata"

    def test_enrichment_with_langfuse_callback_structure(self):
        """Test enrichment with realistic Langfuse callback structure."""
        # Simulate config from create_instrumented_config
        config: RunnableConfig = {
            "callbacks": ["MockLangfuseCallbackHandler"],
            "tags": ["llm_invocation", "router"],
            "metadata": {
                "trace_name": "router_node_call",
                "session_id": "conv_123",
                "user_id": "456",
            },
        }

        # Enrich config
        result = enrich_config_with_node_metadata(config, "router")

        # Verify structure preserved and enriched (MetricsCallback may be auto-added)
        assert "MockLangfuseCallbackHandler" in result["callbacks"]
        assert len(result["callbacks"]) >= 1  # Original + possibly MetricsCallback
        assert result["tags"] == ["llm_invocation", "router"]
        assert result["metadata"]["trace_name"] == "router_node_call"
        assert result["metadata"]["session_id"] == "conv_123"
        assert result["metadata"]["user_id"] == "456"
        assert result["metadata"]["langgraph_node"] == "router"


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_router_node_pattern(self):
        """Simulate router node LLM call pattern."""
        # LangGraph provides config with langgraph_node
        langgraph_config: RunnableConfig = {
            "metadata": {
                "langgraph_node": "router",
                "run_id": "abc123",
            },
            "configurable": {
                "thread_id": "session_456",
            },
        }

        # Node enriches config before LLM call
        enriched_config = enrich_config_with_node_metadata(langgraph_config, "router")

        # Verify metadata ready for callbacks
        assert enriched_config["metadata"]["langgraph_node"] == "router"
        assert enriched_config["metadata"]["run_id"] == "abc123"

    def test_hitl_service_pattern(self):
        """Simulate HITL service LLM call pattern."""
        # HITL service creates instrumented config
        config = create_instrumented_config_from_node(
            llm_type="hitl_classifier",
            session_id="session_789",
            user_id="user_123",
            tags=["hitl", "classification"],
        )

        # Verify config has correct node_name (the key fix for token tracking)
        assert config["metadata"]["langgraph_node"] == "hitl_classifier"

    def test_planner_node_with_custom_config_pattern(self):
        """Simulate planner node with custom LLM config."""
        # Planner node receives config from LangGraph
        node_config: RunnableConfig = {
            "metadata": {"langgraph_node": "planner"},
            "configurable": {"thread_id": "session_abc"},
        }

        # Planner builds config with timeout
        llm_config: RunnableConfig = {
            **node_config,
            "timeout": 120,
        }

        # Enrich before LLM call
        enriched_config = enrich_config_with_node_metadata(llm_config, "planner")

        # Verify all config elements present
        assert enriched_config["metadata"]["langgraph_node"] == "planner"
        assert enriched_config["timeout"] == 120
        assert enriched_config["configurable"]["thread_id"] == "session_abc"

    def test_get_structured_output_integration_pattern(self):
        """Simulate get_structured_output enrichment pattern."""
        # Node calls get_structured_output with config
        node_config: RunnableConfig = {
            "metadata": {"langgraph_node": "router"},
            "callbacks": ["existing_callback"],
        }

        # get_structured_output enriches config
        enriched_config = enrich_config_with_node_metadata(node_config, "router")

        # Verify enrichment doesn't break config structure (MetricsCallback may be added)
        assert enriched_config["metadata"]["langgraph_node"] == "router"
        assert "existing_callback" in enriched_config["callbacks"]
        assert len(enriched_config["callbacks"]) >= 1  # Original + possibly MetricsCallback


# Pytest markers for test organization
pytestmark = pytest.mark.integration
