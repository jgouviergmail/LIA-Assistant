"""
Graph management mixin for AgentService.

Responsibilities:
- Graph lazy initialization
- Agent registry access
- Graph configuration
"""

from typing import TYPE_CHECKING, Any

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class GraphManagementMixin:
    """
    Mixin for graph initialization and management.

    Provides lazy graph building from AgentRegistry configured at startup.
    Ensures graph, store, and HITL components are initialized on first use.
    """

    def __init__(self) -> None:
        """Initialize graph management state."""
        # Graph is built lazily on first use (built from global AgentRegistry)
        # AgentRegistry is configured at application startup (main.py) with
        # checkpointer, store, and all registered agents
        self.graph: Any = None
        self._store: Any = None
        # HITL conversational classifier (lazy init with graph)
        self.hitl_classifier: Any = None
        # HITL question generator (lazy init with graph) - POC implementation
        self.hitl_question_generator: Any = None
        # HITL orchestrator (lazy init with graph) - Phase 3.3 Day 5-6
        self.hitl_orchestrator: Any = None

    async def _ensure_graph_built(self) -> None:
        """
        Lazy graph initialization from AgentRegistry.

        Builds graph on first use with all registered agents, checkpointer,
        and HITL components. Uses global AgentRegistry configured at startup.

        Thread-safe (async context ensures single initialization per service instance).
        """
        if self.graph is not None:
            return

        # Import here to avoid circular dependency
        from src.domains.agents.graph import build_graph
        from src.domains.agents.services.hitl.question_generator import (
            HitlQuestionGenerator,
        )
        from src.domains.agents.services.hitl_classifier import HitlResponseClassifier
        from src.domains.agents.services.hitl_orchestrator import HITLOrchestrator
        from src.domains.agents.utils.hitl_store import HITLStore
        from src.infrastructure.cache.redis import get_redis_cache

        logger.info("building_graph_from_registry")

        # Build graph from registry (includes checkpointer, store, all agents)
        graph_tuple = await build_graph()
        self.graph = graph_tuple[0]  # CompiledStateGraph
        self._store = graph_tuple[1]  # AsyncPostgresStore

        # Initialize HITL components with graph's LLM
        # HITL classifier uses conversational context to classify user responses
        self.hitl_classifier = HitlResponseClassifier()

        # HITL question generator creates dynamic clarification questions (POC)
        self.hitl_question_generator = HitlQuestionGenerator()

        # PHASE 3.3 Day 5-6: Initialize HITLOrchestrator with dependencies
        redis = await get_redis_cache()
        hitl_store = HITLStore(
            redis_client=redis,
            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
        )
        self.hitl_orchestrator = HITLOrchestrator(
            hitl_classifier=self.hitl_classifier,
            hitl_question_generator=self.hitl_question_generator,
            hitl_store=hitl_store,
            graph=self.graph,
            agent_type="generic",  # Will be updated per agent execution
        )

        logger.info(
            "graph_built_successfully",
            agents_registered=len(self.graph.nodes) if hasattr(self.graph, "nodes") else "unknown",
        )

    @staticmethod
    def _get_agents_bucket_label(agents_count: int) -> str:
        """
        Get Prometheus label bucket for agent count metrics.

        Buckets: 1, 2-5, 6-10, 11+

        Args:
            agents_count: Number of agents in conversation

        Returns:
            Bucket label string for Prometheus metrics
        """
        if agents_count == 1:
            return "1"
        elif agents_count <= 5:
            return "2-5"
        elif agents_count <= 10:
            return "6-10"
        else:
            return "11+"
