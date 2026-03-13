"""
Architecture v3.2 - Intelligence, Autonomy, Relevance.

This module contains all v3 components for the agent system.
V3 is now the DEFAULT and ONLY implementation.

Components:
1. QueryIntelligence - Enhanced query analysis with user goals
2. QueryAnalyzerService - Unified LLM-based query analysis (v3.2 fusion)
3. SmartCatalogueService - Filtered tool catalogues (96% token reduction)
4. SmartPlannerService - Template-based + generative planning
5. AutonomousExecutor - Self-healing execution with safeguards
6. RelevanceEngine - Smart result ranking with episodic memory
7. FeedbackLoopService - Learning from recovery patterns (Redis persistence)
8. SemanticPivotService - Query translation to English for optimal LLM processing
9. DisplayConfig - Warm, responsive formatting

REMOVED (v3.2 cleanup - 2026-01):
- QueryIntelligenceService: Merged into QueryAnalyzerService

Usage:
    from src.domains.agents.v3 import (
        get_query_analyzer_service,
        get_smart_planner_service,
        get_autonomous_executor,
        get_relevance_engine,
        get_feedback_loop_service,
        get_semantic_pivot_service,
    )

Note: Legacy nodes (router_node.py, planner_node.py) have been removed.
      V3 is now the default implementation - no feature flags needed.
"""

# Analysis
from src.domains.agents.analysis.query_intelligence import (
    ClarificationRequest,
    QueryIntelligence,
    SemanticFallback,
    ToolFilter,
    UserGoal,
)

# Display
from src.domains.agents.display.config import (
    DisplayConfig,
    DisplayContext,
    UserExpertise,
    Viewport,
)
from src.domains.agents.nodes.planner_node_v3 import (
    planner_node,  # Alias for backward compatibility
    planner_node_v3,
)

# ResponseFormatter removed - pure HTML mode only
# Nodes (v3 is now the default implementation)
from src.domains.agents.nodes.router_node_v3 import (
    router_node,  # Alias for backward compatibility
    router_node_v3,
)
from src.domains.agents.services.autonomous_executor import (
    AutonomousExecutionResult,
    AutonomousExecutor,
    ExecutionAttempt,
    RecoveryStrategy,
    get_autonomous_executor,
)
from src.domains.agents.services.feedback_loop import (
    FeedbackLoopService,
    InMemoryRecoveryStorage,
    PatternMatch,
    RecoveryOutcome,
    RecoveryRecord,
    RecoveryStorage,
    RedisRecoveryStorage,
    get_feedback_loop_service,
)

# Services
from src.domains.agents.services.query_analyzer_service import (
    QueryAnalyzerService,
    get_query_analyzer_service,
)
from src.domains.agents.services.relevance_engine import (
    FilteredResults,
    RankedResult,
    RelevanceEngine,
    UserContext,
    UserMemoryService,
    get_relevance_engine,
    get_user_memory_service,
)
from src.domains.agents.services.semantic_pivot_service import (
    SemanticPivotService,
    get_semantic_pivot_service,
    translate_to_english,
)
from src.domains.agents.services.smart_catalogue_service import (
    FilteredCatalogue,
    SmartCatalogueService,
    get_smart_catalogue_service,
)
from src.domains.agents.services.smart_planner_service import (
    PlanningResult,
    SmartPlannerService,
    get_smart_planner_service,
)

__all__ = [
    # Analysis
    "ClarificationRequest",
    "QueryIntelligence",
    "SemanticFallback",
    "ToolFilter",
    "UserGoal",
    # Services
    "QueryAnalyzerService",
    "get_query_analyzer_service",
    "FilteredCatalogue",
    "SmartCatalogueService",
    "get_smart_catalogue_service",
    "PlanningResult",
    "SmartPlannerService",
    "get_smart_planner_service",
    "AutonomousExecutionResult",
    "AutonomousExecutor",
    "ExecutionAttempt",
    "RecoveryStrategy",
    "get_autonomous_executor",
    "FilteredResults",
    "RankedResult",
    "RelevanceEngine",
    "UserContext",
    "UserMemoryService",
    "get_relevance_engine",
    "get_user_memory_service",
    "FeedbackLoopService",
    "InMemoryRecoveryStorage",
    "PatternMatch",
    "RecoveryOutcome",
    "RecoveryRecord",
    "RecoveryStorage",
    "RedisRecoveryStorage",
    "get_feedback_loop_service",
    # Semantic Pivot
    "SemanticPivotService",
    "get_semantic_pivot_service",
    "translate_to_english",
    # Display
    "DisplayConfig",
    "DisplayContext",
    "UserExpertise",
    "Viewport",
    # Nodes (v3 is now the default)
    "router_node",
    "router_node_v3",
    "planner_node",
    "planner_node_v3",
]
