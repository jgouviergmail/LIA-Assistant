"""
Unit tests for GraphManagementMixin.

Tests graph initialization and agent bucketing logic.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.domains.agents.api.mixins.graph_management import GraphManagementMixin


# Common fixture for patching all imports in _ensure_graph_built
@pytest.fixture
def mock_graph_dependencies():
    """Patch all dependencies imported inside _ensure_graph_built().

    Since imports happen inside the method (local imports), we must patch
    at the SOURCE modules where the classes/functions are defined.
    """
    with (
        patch(
            "src.domains.agents.graph.build_graph",
            new_callable=AsyncMock,
        ) as mock_build,
        patch(
            "src.domains.agents.services.hitl_classifier.HitlResponseClassifier"
        ) as mock_classifier_class,
        patch(
            "src.domains.agents.services.hitl.question_generator.HitlQuestionGenerator"
        ) as mock_question_gen_class,
        patch(
            "src.domains.agents.services.hitl_orchestrator.HITLOrchestrator"
        ) as mock_orchestrator_class,
        patch("src.domains.agents.utils.hitl_store.HITLStore") as mock_store_class,
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new_callable=AsyncMock,
        ) as mock_redis,
    ):
        # Setup default mock return values
        mock_graph = Mock()
        mock_graph.nodes = {"node1": Mock(), "node2": Mock(), "node3": Mock()}
        mock_store = Mock()
        mock_build.return_value = (mock_graph, mock_store)

        mock_classifier_class.return_value = Mock()
        mock_question_gen_class.return_value = Mock()
        mock_store_class.return_value = Mock()
        mock_orchestrator_class.return_value = Mock()
        mock_redis.return_value = Mock()

        yield {
            "build_graph": mock_build,
            "classifier_class": mock_classifier_class,
            "question_gen_class": mock_question_gen_class,
            "orchestrator_class": mock_orchestrator_class,
            "store_class": mock_store_class,
            "redis": mock_redis,
            "graph": mock_graph,
            "store": mock_store,
        }


class TestGraphManagementMixin:
    """Test suite for GraphManagementMixin."""

    # ==================== _get_agents_bucket_label Tests ====================

    def test_get_agents_bucket_label_single_agent(self):
        """Test bucket label for single agent."""
        result = GraphManagementMixin._get_agents_bucket_label(1)
        assert result == "1"

    def test_get_agents_bucket_label_two_agents(self):
        """Test bucket label for 2 agents."""
        result = GraphManagementMixin._get_agents_bucket_label(2)
        assert result == "2-5"

    def test_get_agents_bucket_label_five_agents(self):
        """Test bucket label for 5 agents (boundary)."""
        result = GraphManagementMixin._get_agents_bucket_label(5)
        assert result == "2-5"

    def test_get_agents_bucket_label_six_agents(self):
        """Test bucket label for 6 agents."""
        result = GraphManagementMixin._get_agents_bucket_label(6)
        assert result == "6-10"

    def test_get_agents_bucket_label_ten_agents(self):
        """Test bucket label for 10 agents (boundary)."""
        result = GraphManagementMixin._get_agents_bucket_label(10)
        assert result == "6-10"

    def test_get_agents_bucket_label_eleven_agents(self):
        """Test bucket label for 11 agents."""
        result = GraphManagementMixin._get_agents_bucket_label(11)
        assert result == "11+"

    def test_get_agents_bucket_label_many_agents(self):
        """Test bucket label for many agents."""
        result = GraphManagementMixin._get_agents_bucket_label(100)
        assert result == "11+"

    def test_get_agents_bucket_label_zero_agents(self):
        """Test bucket label for zero agents (edge case).

        Zero agents: 0 != 1, but 0 <= 5, so it falls into "2-5" bucket.
        """
        result = GraphManagementMixin._get_agents_bucket_label(0)
        assert result == "2-5"

    # ==================== __init__ Tests ====================

    def test_init_initializes_attributes(self):
        """Test that __init__ properly initializes all attributes."""
        mixin = GraphManagementMixin()

        assert mixin.graph is None
        assert mixin._store is None
        assert mixin.hitl_classifier is None
        assert mixin.hitl_question_generator is None

    # ==================== _ensure_graph_built Tests ====================

    @pytest.mark.asyncio
    async def test_ensure_graph_built_first_call(self, mock_graph_dependencies):
        """Test graph is built on first call to _ensure_graph_built."""
        mocks = mock_graph_dependencies

        # Test
        mixin = GraphManagementMixin()
        assert mixin.graph is None

        await mixin._ensure_graph_built()

        # Verify graph was built
        assert mixin.graph is mocks["graph"]
        assert mixin._store is mocks["store"]
        assert mixin.hitl_classifier is mocks["classifier_class"].return_value
        assert mixin.hitl_question_generator is mocks["question_gen_class"].return_value

        # Verify build_graph was called
        mocks["build_graph"].assert_called_once()
        mocks["classifier_class"].assert_called_once()
        mocks["question_gen_class"].assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_graph_built_subsequent_calls(self, mock_graph_dependencies):
        """Test graph is not rebuilt on subsequent calls."""
        mocks = mock_graph_dependencies

        # Test
        mixin = GraphManagementMixin()
        mixin.graph = Mock()  # Simulate already built

        await mixin._ensure_graph_built()

        # Verify build_graph was NOT called
        mocks["build_graph"].assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_graph_built_handles_graph_without_nodes_attribute(
        self, mock_graph_dependencies
    ):
        """Test graph building handles graph object without nodes attribute."""
        mocks = mock_graph_dependencies
        # Reconfigure mock graph without nodes attribute
        mock_graph = Mock(spec=[])  # Empty spec = no attributes
        mocks["build_graph"].return_value = (mock_graph, Mock())

        # Test
        mixin = GraphManagementMixin()
        await mixin._ensure_graph_built()

        # Should not raise - logs "unknown" for agents_registered
        assert mixin.graph is mock_graph

    @pytest.mark.asyncio
    async def test_ensure_graph_built_initializes_hitl_components(self, mock_graph_dependencies):
        """Test HITL components are properly initialized."""
        mocks = mock_graph_dependencies

        # Setup specific mock instances
        mock_classifier = Mock(name="classifier")
        mock_question_gen = Mock(name="question_gen")
        mocks["classifier_class"].return_value = mock_classifier
        mocks["question_gen_class"].return_value = mock_question_gen

        # Test
        mixin = GraphManagementMixin()
        await mixin._ensure_graph_built()

        # Verify HITL components were initialized
        assert mixin.hitl_classifier is mock_classifier
        assert mixin.hitl_question_generator is mock_question_gen
        mocks["classifier_class"].assert_called_once_with()
        mocks["question_gen_class"].assert_called_once_with()

    @pytest.mark.asyncio
    async def test_ensure_graph_built_extracts_tuple_correctly(self, mock_graph_dependencies):
        """Test that graph tuple unpacking is correct."""
        mocks = mock_graph_dependencies

        # Setup specific mock instances with required attributes
        expected_graph = Mock(name="graph")
        expected_graph.nodes = {"node1": Mock()}  # Required for logging
        expected_store = Mock(name="store")
        mocks["build_graph"].return_value = (expected_graph, expected_store)

        # Test
        mixin = GraphManagementMixin()
        await mixin._ensure_graph_built()

        # Verify tuple was unpacked correctly
        assert mixin.graph is expected_graph
        assert mixin._store is expected_store

    @pytest.mark.asyncio
    async def test_ensure_graph_built_initializes_hitl_orchestrator(self, mock_graph_dependencies):
        """Test that HITLOrchestrator is properly initialized."""
        mocks = mock_graph_dependencies

        # Test
        mixin = GraphManagementMixin()
        await mixin._ensure_graph_built()

        # Verify HITLOrchestrator was initialized with correct dependencies
        mocks["orchestrator_class"].assert_called_once()
        call_kwargs = mocks["orchestrator_class"].call_args.kwargs
        assert "hitl_classifier" in call_kwargs
        assert "hitl_question_generator" in call_kwargs
        assert "hitl_store" in call_kwargs
        assert "graph" in call_kwargs
        assert call_kwargs["agent_type"] == "generic"


class TestGraphManagementMixinIntegrationBehavior:
    """Test suite for GraphManagementMixin integration behaviors."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_ensure_calls_idempotent(self, mock_graph_dependencies):
        """Test that multiple concurrent ensure_graph_built calls are idempotent."""
        mocks = mock_graph_dependencies

        # Test
        mixin = GraphManagementMixin()

        # First call builds
        await mixin._ensure_graph_built()
        first_graph = mixin.graph

        # Subsequent calls should not rebuild
        await mixin._ensure_graph_built()
        await mixin._ensure_graph_built()

        # Verify only one build
        assert mocks["build_graph"].call_count == 1
        assert mixin.graph is first_graph  # Same instance

    def test_bucket_label_boundary_values_comprehensive(self):
        """Comprehensive test of all bucket boundary values."""
        test_cases = [
            (0, "2-5"),  # Edge case: zero agents (0 <= 5)
            (1, "1"),  # Single agent
            (2, "2-5"),  # Start of 2-5 bucket
            (3, "2-5"),
            (4, "2-5"),
            (5, "2-5"),  # End of 2-5 bucket
            (6, "6-10"),  # Start of 6-10 bucket
            (7, "6-10"),
            (8, "6-10"),
            (9, "6-10"),
            (10, "6-10"),  # End of 6-10 bucket
            (11, "11+"),  # Start of 11+ bucket
            (15, "11+"),
            (50, "11+"),
            (100, "11+"),
            (1000, "11+"),
        ]

        for count, expected_bucket in test_cases:
            result = GraphManagementMixin._get_agents_bucket_label(count)
            assert (
                result == expected_bucket
            ), f"Failed for count={count}: expected {expected_bucket}, got {result}"
