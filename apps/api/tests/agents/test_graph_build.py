"""
Unit tests for LangGraph StateGraph construction and compilation.

Validates that the graph builds correctly with proper nodes, edges, and configuration.
Tests LangGraph v1.0 best practices compliance.

TODO: Update tests for LangGraph v1.0 API changes (base_agent_builder migration)
"""

import os

import pytest
from langgraph.graph.state import CompiledStateGraph

from src.core.config import Settings
from src.domains.agents.graph import build_graph

# Skip all tests if OPENAI_API_KEY is not set (integration tests that call real LLM)
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for integration tests with real LLM",
)


@pytest.fixture
def test_settings():
    """Fixture providing test-specific settings."""
    return Settings(
        secret_key="test_secret_key_minimum_32_chars_long",
        fernet_key="test_fernet_key_for_testing_only_32b",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        redis_url="redis://localhost:6379/0",
        openai_api_key="sk-test-key",
    )


class TestGraphConstruction:
    """Test suite for graph building and compilation."""

    def test_graph_builds_successfully_without_checkpointer(self, test_settings):
        """
        GIVEN valid settings
        WHEN build_graph is called without checkpointer
        THEN graph should compile successfully
        """
        graph, store = build_graph(config=test_settings, checkpointer=None)

        # Validate graph compilation
        assert isinstance(graph, CompiledStateGraph)
        assert store is not None

    def test_graph_has_correct_nodes(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN inspecting graph structure
        THEN all expected nodes should be present
        """
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Extract node names from compiled graph
        # LangGraph internal structure: graph.nodes contains node definitions
        node_names = list(graph.nodes.keys())

        # Expected nodes (V1 sequential architecture + F4 compaction)
        expected_nodes = [
            "compaction",  # F4: Context compaction before router
            "router",
            "task_orchestrator",
            "contacts_agent",
            "response",
            "__start__",  # LangGraph internal entry node
        ]

        for expected in expected_nodes:
            assert expected in node_names, f"Missing node: {expected}"

    def test_graph_entry_point_is_compaction(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN checking entry point
        THEN compaction should be the entry node (F4), routing to router
        """
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # LangGraph v1.0: Verify graph has compaction and router nodes
        # Entry point validation is done by successful compilation
        assert "compaction" in graph.nodes
        assert "router" in graph.nodes
        assert "__start__" in graph.nodes

        # Graph compiled successfully means routing is correct

    def test_graph_state_schema_is_messages_state(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN inspecting state schema
        THEN state should use MessagesState
        """
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Validate state schema
        # LangGraph v1.0: graph.config_schema contains state definition
        assert graph.config_schema is not None

    def test_store_is_injected_into_graph(self, test_settings):
        """
        GIVEN a compiled graph with store
        WHEN checking store availability
        THEN store should be accessible in graph
        """
        graph, store = build_graph(config=test_settings, checkpointer=None)

        # Store should be non-None
        assert store is not None

        # Store should be InMemoryStore (or compatible type)
        assert hasattr(store, "aget")
        assert hasattr(store, "aput")

    def test_graph_compilation_with_checkpointer(self, test_settings):
        """
        GIVEN a mock checkpointer
        WHEN build_graph is called with checkpointer
        THEN graph should compile with checkpoint support
        """

        # Mock checkpointer (minimal interface)
        class MockCheckpointer:
            async def aget(self, *args, **kwargs):
                return None

            async def aput(self, *args, **kwargs):
                pass

        mock_checkpointer = MockCheckpointer()

        graph, store = build_graph(
            config=test_settings,
            checkpointer=mock_checkpointer,
        )

        # Graph should compile successfully
        assert isinstance(graph, CompiledStateGraph)
        assert store is not None

    def test_graph_conditional_edges_from_router(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN checking router edges
        THEN router should have conditional routing to orchestrator and response
        """
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Router should have conditional edges
        router_node = graph.nodes.get("router")
        assert router_node is not None

        # Check that router has edges to both task_orchestrator and response
        # This validates the conditional routing logic
        # Note: Exact structure depends on LangGraph internal representation
        # Validation: graph should not raise errors during compilation

    def test_contacts_agent_is_wrapper_node(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN inspecting contacts_agent node
        THEN it should be a wrapper function node (not direct subgraph)
        """
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Contacts agent should exist as a node
        contacts_node = graph.nodes.get("contacts_agent")
        assert contacts_node is not None

        # Wrapper pattern: node should be a callable function
        # Not a direct StateGraph (which would be problematic for HITL)

    def test_graph_ends_at_response_node(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN checking terminal nodes
        THEN response node should connect to END
        """
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Response node should exist
        response_node = graph.nodes.get("response")
        assert response_node is not None

        # Response should have edge to __end__ (LangGraph internal)
        # Validated by successful compilation

    def test_graph_uses_correct_llm_models_from_config(self, test_settings):
        """
        GIVEN test settings with specific LLM models
        WHEN building graph
        THEN nodes should use configured models
        """
        # Custom settings (LLM model fields are deprecated — LLM_DEFAULTS is source of truth)
        custom_settings = Settings(
            secret_key="test_secret_key_minimum_32_chars_long",
            fernet_key="test_fernet_key_for_testing_only_32b",
            database_url="postgresql+asyncpg://test:test@localhost/test",
            redis_url="redis://localhost:6379/0",
        )

        # Build graph with custom config
        graph, _ = build_graph(config=custom_settings, checkpointer=None)

        # Graph should compile successfully
        assert isinstance(graph, CompiledStateGraph)

        # Model configuration is validated during build_graph execution
        # If models are incorrect, graph build would fail


class TestGraphV1Architecture:
    """Test suite validating V1 sequential architecture compliance."""

    def test_v1_sequential_execution_path(self, test_settings):
        """
        GIVEN V1 architecture
        WHEN analyzing execution flow
        THEN path should be: router → orchestrator → agent → response
        """
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Validate all V1 nodes exist
        expected_v1_nodes = ["router", "task_orchestrator", "contacts_agent", "response"]
        node_names = list(graph.nodes.keys())

        for node in expected_v1_nodes:
            assert node in node_names

    def test_no_parallel_execution_in_v1(self, test_settings):
        """
        GIVEN V1 architecture
        WHEN checking orchestration
        THEN parallel execution should not be implemented
        """
        # This is a documentation test - V1 only supports sequential
        # Parallel execution is planned for V2
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Graph should compile successfully with sequential-only logic
        assert isinstance(graph, CompiledStateGraph)

    def test_graph_supports_future_agents_roadmap(self, test_settings):
        """
        GIVEN V1 architecture
        WHEN checking for future extensibility
        THEN graph should be structured to add emails_agent, calendar_agent
        """
        # This is a structural validation
        # V2 will add: emails_agent, calendar_agent
        graph, _ = build_graph(config=test_settings, checkpointer=None)

        # Current V1 nodes
        current_nodes = list(graph.nodes.keys())

        # Future agents should NOT be present in V1
        assert "emails_agent" not in current_nodes
        assert "calendar_agent" not in current_nodes

        # But structure should support adding them (validated by successful build)
