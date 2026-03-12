"""
Analysis services for query intelligence.

This package contains specialized services extracted from QueryAnalyzerService
to follow SRP (Single Responsibility Principle) and SoC (Separation of Concerns).

Architecture:
- MemoryResolver: Handles memory facts retrieval and reference resolution
- GoalInferrer: Infers user goal from query and context
- RoutingDecider: Decides routing based on intent, domains, and scores

Note: Context resolution is already handled by ContextResolutionService (external service),
so no additional ContextResolver is needed (YAGNI principle).

These services are composed in QueryAnalyzerService via Composition pattern.
"""

from src.domains.agents.services.analysis.goal_inferrer import (
    GoalInferrer,
    get_goal_inferrer,
)
from src.domains.agents.services.analysis.memory_resolver import (
    MemoryResolver,
    get_memory_resolver,
)
from src.domains.agents.services.analysis.routing_decider import (
    RoutingDecider,
    get_routing_decider,
)

__all__ = [
    "MemoryResolver",
    "GoalInferrer",
    "RoutingDecider",
    "get_memory_resolver",
    "get_goal_inferrer",
    "get_routing_decider",
]
