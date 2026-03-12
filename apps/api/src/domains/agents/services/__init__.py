"""
Agent services module.

Architecture v3.2 - Unified Query Analysis.

Contains service classes for agent-related functionality:
- HitlResponseClassifier: Natural language classification for HITL interactions
- TokenCounterService: Pre-count tokens before LLM invocation
- SmartPlannerService: v3 template-based + generative planning (89% token reduction)
- SmartCatalogueService: v3 filtered tool catalogues (96% token reduction)
- ContextResolutionService: Turn-based context management for follow-up questions
- ReferenceResolver: Linguistic reference extraction and resolution
- SemanticToolSelector: LLM-Native semantic tool selection via embeddings (Phase 1)
- QueryAnalyzerService: v3.2 Unified LLM-based analysis + routing (merged QueryIntelligenceService)

REMOVED (v3.2 cleanup - 2026-01):
- QueryIntelligenceService: Merged into QueryAnalyzerService
- SemanticDomainSelector: Deleted - replaced by QueryAnalyzerService (LLM-based)
- SemanticIntentDetector: Deleted - replaced by QueryAnalyzerService (LLM-based)

NOTE: Legacy PlannerService removed (2025-12-30) - replaced by SmartPlannerService.
"""

from src.domains.agents.services.context_resolution_service import (
    ContextResolutionService,
    get_context_resolution_service,
    reset_context_resolution_service,
)
from src.domains.agents.services.hitl_classifier import (
    ClassificationResult,
    HitlResponseClassifier,
)
from src.domains.agents.services.knowledge_enrichment_service import (
    KnowledgeContext,
    KnowledgeEnrichmentService,
    get_knowledge_enrichment_service,
    reset_knowledge_enrichment_service,
)
from src.domains.agents.services.memory_reference_resolution_service import (
    MemoryReferenceResolutionService,
    ResolvedReferences,
    get_memory_reference_resolution_service,
    reset_memory_reference_resolution_service,
)
from src.domains.agents.services.query_analyzer_service import (
    QueryAnalysisResult,
    QueryAnalyzerService,
    analyze_query,
    get_query_analyzer_service,
    reset_query_analyzer_service,
)
from src.domains.agents.services.reference_resolver import (
    ExtractedReference,
    ExtractedReferences,
    ReferenceResolver,
    ResolvedContext,
    get_reference_resolver,
    reset_reference_resolver,
)
from src.domains.agents.services.semantic_pivot_service import (
    SemanticPivotService,
    get_semantic_pivot_service,
    reset_semantic_pivot_service,
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
from src.domains.agents.services.token_counter_service import (
    FallbackLevel,
    TokenCounterService,
    get_token_counter,
)
from src.domains.agents.services.tool_selector import (
    DEFAULT_HARD_THRESHOLD,
    DEFAULT_MAX_TOOLS,
    DEFAULT_SOFT_THRESHOLD,
    SemanticToolSelector,
    ToolMatch,
    ToolSelectionResult,
    get_tool_selector,
    initialize_tool_selector,
    reset_tool_selector,
)

__all__ = [
    # Core services
    "ClassificationResult",
    "ContextResolutionService",
    "HitlResponseClassifier",
    # Knowledge Enrichment (Brave Search)
    "KnowledgeContext",
    "KnowledgeEnrichmentService",
    "get_knowledge_enrichment_service",
    "reset_knowledge_enrichment_service",
    "MemoryReferenceResolutionService",
    "ReferenceResolver",
    "ResolvedContext",
    "ResolvedReferences",
    "TokenCounterService",
    # v3.2 Services (Unified LLM-Based Intelligence)
    "QueryAnalysisResult",
    "QueryAnalyzerService",
    "analyze_query",
    "get_query_analyzer_service",
    "reset_query_analyzer_service",
    # v3 Services (Architecture v3)
    "FilteredCatalogue",
    "PlanningResult",
    "SemanticPivotService",
    "SmartCatalogueService",
    "SmartPlannerService",
    "get_semantic_pivot_service",
    "get_smart_catalogue_service",
    "get_smart_planner_service",
    "reset_semantic_pivot_service",
    "translate_to_english",
    # Semantic services (SemanticToolSelector still in use)
    "DEFAULT_HARD_THRESHOLD",
    "DEFAULT_MAX_TOOLS",
    "DEFAULT_SOFT_THRESHOLD",
    "SemanticToolSelector",
    "ToolMatch",
    "ToolSelectionResult",
    "get_tool_selector",
    "initialize_tool_selector",
    "reset_tool_selector",
    # Reference services
    "ExtractedReference",
    "ExtractedReferences",
    "FallbackLevel",
    "get_context_resolution_service",
    "get_memory_reference_resolution_service",
    "get_reference_resolver",
    "get_token_counter",
    "reset_context_resolution_service",
    "reset_memory_reference_resolution_service",
    "reset_reference_resolver",
]
