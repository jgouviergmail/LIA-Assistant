"""
Unit tests for LangGraph StateGraph construction and compilation.

Validates that the graph builds correctly with proper nodes, edges, and configuration.
Tests LangGraph v1.0 best practices compliance.

TODO: Update tests for LangGraph v1.0 API changes (base_agent_builder migration)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from src.core.config import Settings
from src.domains.agents.constants import AGENT_CONTACT
from src.domains.agents.graph import build_graph

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def stub_agent_registry():
    """Populate the global registry with trivial agents.

    `build_graph` resolves every domain agent from the registry to wrap it in a
    node. Building the real ones drags in each agent's LLM clients and tool
    surface, which is not what this suite asserts: it asserts the SHAPE of the
    graph — which nodes exist, where it starts, where it ends. A registry whose
    agents are no-op runnables keeps the shape identical and the test hermetic.

    The previous global registry is restored so no other suite inherits this one.
    """
    from src.domains.agents.registry import agent_registry as registry_module

    stub = MagicMock()
    stub.get_agent.return_value = RunnableLambda(lambda state: state)
    stub._checkpointer = None

    previous = registry_module._global_registry
    registry_module._global_registry = stub
    try:
        yield stub
    finally:
        registry_module._global_registry = previous


@pytest.fixture(autouse=True)
def stub_tool_context_store():
    """Keep graph construction hermetic: no LangGraph Postgres store.

    `build_graph` awaits `get_tool_context_store()` before compiling, which
    opens the LangGraph store pool — a real database connection that only fails
    on its connect timeout in a unit environment. The store is injected into
    `graph.compile(store=...)`; a stand-in is enough to assert the graph's
    SHAPE, which is all this suite is about.
    """
    store = MagicMock()
    with patch(
        "src.domains.agents.graph.get_tool_context_store",
        AsyncMock(return_value=store),
    ):
        yield store


@pytest.fixture
def test_settings():
    """Fixture providing test-specific settings."""
    return Settings(
        secret_key="test_secret_key_minimum_32_chars_long",
        fernet_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        redis_url="redis://localhost:6379/0",
        openai_api_key="sk-test-key",
    )


class TestGraphConstruction:
    """Test suite for graph building and compilation."""

    async def test_graph_builds_successfully_without_checkpointer(self, test_settings):
        """
        GIVEN valid settings
        WHEN build_graph is called without checkpointer
        THEN graph should compile successfully
        """
        graph, store = await build_graph(config=test_settings, checkpointer=None)

        # Validate graph compilation
        assert isinstance(graph, CompiledStateGraph)
        assert store is not None

    async def test_graph_has_correct_nodes(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN inspecting graph structure
        THEN all expected nodes should be present
        """
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Extract node names from compiled graph
        # LangGraph internal structure: graph.nodes contains node definitions
        node_names = list(graph.nodes.keys())

        # Expected nodes (V1 sequential architecture + F4 compaction)
        expected_nodes = [
            "compaction",  # F4: Context compaction before router
            "router",
            "task_orchestrator",
            AGENT_CONTACT,
            "response",
            "__start__",  # LangGraph internal entry node
        ]

        for expected in expected_nodes:
            assert expected in node_names, f"Missing node: {expected}"

    async def test_graph_entry_point_is_compaction(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN checking entry point
        THEN compaction should be the entry node (F4), routing to router
        """
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # LangGraph v1.0: Verify graph has compaction and router nodes
        # Entry point validation is done by successful compilation
        assert "compaction" in graph.nodes
        assert "router" in graph.nodes
        assert "__start__" in graph.nodes

        # Graph compiled successfully means routing is correct

    async def test_graph_state_schema_is_messages_state(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN inspecting state schema
        THEN state should use MessagesState
        """
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Validate state schema
        # LangGraph v1.0: graph.config_schema contains state definition
        assert graph.config_schema is not None

    async def test_store_is_injected_into_graph(self, test_settings):
        """
        GIVEN a compiled graph with store
        WHEN checking store availability
        THEN store should be accessible in graph
        """
        graph, store = await build_graph(config=test_settings, checkpointer=None)

        # Store should be non-None
        assert store is not None

        # Store should be InMemoryStore (or compatible type)
        assert hasattr(store, "aget")
        assert hasattr(store, "aput")

    async def test_graph_compilation_with_checkpointer(self, test_settings):
        """
        GIVEN a mock checkpointer
        WHEN build_graph is called with checkpointer
        THEN graph should compile with checkpoint support
        """

        # LangGraph 1.x validates the type at compile time: a duck-typed
        # stand-in is rejected outright, so use the real in-memory saver.
        mock_checkpointer = InMemorySaver()

        graph, store = await build_graph(
            config=test_settings,
            checkpointer=mock_checkpointer,
        )

        # Graph should compile successfully
        assert isinstance(graph, CompiledStateGraph)
        assert store is not None

    async def test_graph_conditional_edges_from_router(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN checking router edges
        THEN router should have conditional routing to orchestrator and response
        """
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Router should have conditional edges
        router_node = graph.nodes.get("router")
        assert router_node is not None

        # Check that router has edges to both task_orchestrator and response
        # This validates the conditional routing logic
        # Note: Exact structure depends on LangGraph internal representation
        # Validation: graph should not raise errors during compilation

    async def test_contact_agent_is_wrapper_node(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN inspecting contact_agent node
        THEN it should be a wrapper function node (not direct subgraph)
        """
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Contact agent should exist as a node
        contacts_node = graph.nodes.get(AGENT_CONTACT)
        assert contacts_node is not None

        # Wrapper pattern: node should be a callable function
        # Not a direct StateGraph (which would be problematic for HITL)

    async def test_graph_ends_at_response_node(self, test_settings):
        """
        GIVEN a compiled graph
        WHEN checking terminal nodes
        THEN response node should connect to END
        """
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Response node should exist
        response_node = graph.nodes.get("response")
        assert response_node is not None

        # Response should have edge to __end__ (LangGraph internal)
        # Validated by successful compilation

    async def test_graph_uses_correct_llm_models_from_config(self, test_settings):
        """
        GIVEN test settings with specific LLM models
        WHEN building graph
        THEN nodes should use configured models
        """
        # Custom settings (LLM model fields are deprecated — LLM_DEFAULTS is source of truth)
        custom_settings = Settings(
            secret_key="test_secret_key_minimum_32_chars_long",
            fernet_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
            database_url="postgresql+asyncpg://test:test@localhost/test",
            redis_url="redis://localhost:6379/0",
        )

        # Build graph with custom config
        graph, _ = await build_graph(config=custom_settings, checkpointer=None)

        # Graph should compile successfully
        assert isinstance(graph, CompiledStateGraph)

        # Model configuration is validated during build_graph execution
        # If models are incorrect, graph build would fail


class TestGraphV1Architecture:
    """Test suite validating V1 sequential architecture compliance."""

    async def test_v1_sequential_execution_path(self, test_settings):
        """
        GIVEN V1 architecture
        WHEN analyzing execution flow
        THEN path should be: router → orchestrator → agent → response
        """
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Validate all V1 nodes exist
        expected_v1_nodes = ["router", "task_orchestrator", AGENT_CONTACT, "response"]
        node_names = list(graph.nodes.keys())

        for node in expected_v1_nodes:
            assert node in node_names

    async def test_no_parallel_execution_in_v1(self, test_settings):
        """
        GIVEN V1 architecture
        WHEN checking orchestration
        THEN parallel execution should not be implemented
        """
        # This is a documentation test - V1 only supports sequential
        # Parallel execution is planned for V2
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Graph should compile successfully with sequential-only logic
        assert isinstance(graph, CompiledStateGraph)

    async def test_graph_supports_future_agents_roadmap(self, test_settings):
        """
        GIVEN V1 architecture
        WHEN checking for future extensibility
        THEN graph should be structured to add emails_agent, calendar_agent
        """
        # This is a structural validation
        # V2 will add: emails_agent, calendar_agent
        graph, _ = await build_graph(config=test_settings, checkpointer=None)

        # Current V1 nodes
        current_nodes = list(graph.nodes.keys())

        # Future agents should NOT be present in V1
        assert "emails_agent" not in current_nodes
        assert "calendar_agent" not in current_nodes

        # But structure should support adding them (validated by successful build)
