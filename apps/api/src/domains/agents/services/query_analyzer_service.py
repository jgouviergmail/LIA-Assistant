"""
Query Analyzer Service - Unified LLM-based Query Analysis.

Architecture v3.2 - Fusion QueryIntelligenceService + QueryAnalyzerService.

Single service combining:
- LLM-based intent/domain detection (was QueryAnalyzerService)
- Context resolution, routing decision, user goal inference (was QueryIntelligenceService)

Benefits:
1. Single service, single responsibility
2. No wrapper overhead
3. Module-level constants (no rebuild per request)
4. Internalized memory facts retrieval

Performance Target: P95 < 800ms (uses fast LLM model)

Usage:
    from src.domains.agents.services.query_analyzer_service import (
        get_query_analyzer_service,
    )

    analyzer = get_query_analyzer_service()
    intelligence = await analyzer.analyze_full(
        query="Quel temps fait-il chez mon frère ?",
        messages=messages,
        state=state,
        config=config,
    )
    # intelligence.route_to = "planner"
    # intelligence.domains = ["weather", "contacts"]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np
from langchain_core.messages import BaseMessage
from pydantic import BaseModel
from pydantic import Field as PydanticField

from src.core.config import settings
from src.core.config.agents import V3RoutingConfig
from src.core.constants import (
    INTENT_PATTERNS_CREATE,
    INTENT_PATTERNS_DELETE,
    INTENT_PATTERNS_SEND,
    INTENT_PATTERNS_UPDATE,
)
from src.domains.agents.analysis.query_intelligence import (
    QueryIntelligence,
    SemanticFallback,
    UserGoal,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.services.analysis.goal_inferrer import GoalInferrer
    from src.domains.agents.services.analysis.memory_resolver import MemoryResolver
    from src.domains.agents.services.analysis.routing_decider import RoutingDecider
    from src.domains.agents.services.context_resolution_service import (
        ContextResolutionService,
    )
    from src.domains.agents.services.reference_resolver import ResolvedContext

logger = get_logger(__name__)


# =============================================================================
# DOMAIN SOFTMAX CALIBRATION
# =============================================================================


def _apply_domain_softmax_calibration(
    primary_domain: str | None,
    secondary_domains: list[str],
    confidence: float,
    temperature: float = 0.1,
) -> dict[str, float]:
    """Apply softmax calibration to domain scores.

    Primary domain gets full confidence, secondary domains get decreasing weights.
    Then softmax is applied for probability-like distribution.

    Pattern: Same as tool_selector.py _apply_softmax_calibration().

    Args:
        primary_domain: Main detected domain (highest priority).
        secondary_domains: Additional domains (lower priority).
        confidence: Base confidence from LLM analysis.
        temperature: Softmax temperature (lower = sharper discrimination).

    Returns:
        Dict mapping domain names to calibrated scores summing to ~1.0.
    """
    if not primary_domain and not secondary_domains:
        return {}

    # Build domain list with weighted raw scores
    domains: list[str] = []
    raw_scores: list[float] = []

    if primary_domain:
        domains.append(primary_domain)
        raw_scores.append(confidence)

    for i, domain in enumerate(secondary_domains):
        domains.append(domain)
        # Secondary domains: decreasing weight (0.75, 0.6, 0.5, ...)
        weight = max(0.4, 0.75 - (i * 0.15))
        raw_scores.append(confidence * weight)

    if len(domains) == 1:
        return {domains[0]: 1.0}

    # Apply softmax calibration (same pattern as tool_selector.py)
    scores_array = np.array(raw_scores)

    # Stage 1: Min-Max Stretching
    min_score = np.min(scores_array)
    max_score = np.max(scores_array)
    score_range = max_score - min_score

    if score_range < 1e-6:
        # All scores identical - uniform distribution
        return dict.fromkeys(domains, 1.0 / len(domains))

    stretched = (scores_array - min_score) / score_range

    # Stage 2: Softmax with temperature
    scaled = stretched / temperature
    scaled_shifted = scaled - np.max(scaled)  # Prevent overflow
    exp_scores = np.exp(scaled_shifted)
    softmax_scores = exp_scores / np.sum(exp_scores)

    return {d: float(softmax_scores[i]) for i, d in enumerate(domains)}


# =============================================================================
# FOR_EACH POST-PROCESSING HEURISTICS
# =============================================================================

# Explicit iteration patterns (ENGLISH ONLY)
# Note: query is already English-translated by SemanticPivotService
_FOR_EACH_PATTERNS_EXPLICIT: frozenset[str] = frozenset(
    [
        "for each",
        "to each",
        "each of",
        "to all",
        "send to all",
        "delete all",
        "all my",
        "every one",
        "all of them",
        "each one",
        "to everyone",
        "remove all",
    ]
)

# Plural collection nouns indicating potential iteration (ENGLISH ONLY)
_PLURAL_COLLECTION_HINTS: frozenset[str] = frozenset(
    [
        "contacts",
        "emails",
        "events",
        "tasks",
        "files",
        "places",
        "messages",
        "meetings",
        "appointments",
        "documents",
    ]
)

# Domain to collection key mapping
_DOMAIN_TO_COLLECTION: dict[str, str] = {
    "contact": "contacts",
    "email": "emails",
    "event": "events",
    "task": "tasks",
    "file": "files",
    "place": "places",
}


def _apply_for_each_heuristics(
    result: QueryAnalysisResult,
    query_lower: str,
    domains: list[str],
) -> QueryAnalysisResult:
    """Enhance FOR_EACH detection with post-LLM heuristics.

    The LLM may miss FOR_EACH patterns due to implicit iteration
    (plural subjects + action verb) or quantifiers without explicit
    "for each" wording.

    Heuristics applied (ENGLISH patterns only, query is pre-translated):
    1. Explicit patterns: "for each", "to all", "all my"
    2. Plural noun + mutation intent: "send to contacts"
    3. Quantifier + mutation: "delete the first 5"

    Args:
        result: Original QueryAnalysisResult from LLM.
        query_lower: Lowercased query string (English-translated).
        domains: Detected domains.

    Returns:
        Possibly enhanced QueryAnalysisResult with for_each_detected=True.
    """
    # Already detected by LLM - trust it
    if result.for_each_detected:
        return result

    # Heuristic 1: Explicit patterns
    has_explicit = any(p in query_lower for p in _FOR_EACH_PATTERNS_EXPLICIT)

    # Heuristic 2: Plural collection noun + mutation intent
    has_plural = any(p in query_lower for p in _PLURAL_COLLECTION_HINTS)
    has_mutation = result.is_mutation_intent

    # Heuristic 3: Quantifier + mutation ("delete the first 3 tasks")
    # \d+ requires at least one digit after ordinal word.
    # Without this, "the first task" (ordinal selection) falsely triggers FOR_EACH.
    has_quantifier = bool(
        re.search(
            r"\b(the|my)\s+(\d+\s+)?(first|last|top|bottom)\s+\d+\b",
            query_lower,
        )
    )

    # Decision logic
    should_enhance = (
        has_explicit or (has_plural and has_mutation) or (has_quantifier and has_mutation)
    )

    if not should_enhance:
        return result

    # Infer collection key from domains
    collection_key = result.for_each_collection_key
    if not collection_key:
        for domain in domains:
            if domain in _DOMAIN_TO_COLLECTION:
                collection_key = _DOMAIN_TO_COLLECTION[domain]
                break

    logger.info(
        "for_each_heuristics_applied",
        query_preview=query_lower[:50],
        has_explicit=has_explicit,
        has_plural=has_plural,
        has_mutation=has_mutation,
        has_quantifier=has_quantifier,
        collection_key=collection_key,
    )

    # Update constraint_hints
    enhanced_hints = dict(result.constraint_hints)
    enhanced_hints["has_iteration"] = True

    return replace(
        result,
        for_each_detected=True,
        for_each_collection_key=collection_key,
        has_cardinality_risk=True,
        constraint_hints=enhanced_hints,
    )


# =============================================================================
# OUTPUT SCHEMA (Pydantic for structured output)
# =============================================================================


class ResolvedReference(BaseModel):
    """A resolved reference from the query."""

    original: str = PydanticField(description="Original reference in user query")
    resolved: str = PydanticField(description="Resolved value")
    type: str = PydanticField(description="Reference type: temporal, person, contextual")


class ConstraintHints(BaseModel):
    """Detected constraints in user query for filtering results.

    OpenAI structured output requires explicit field definitions.
    Using dict[str, bool] generates additionalProperties which is incompatible.
    """

    has_distance: bool = PydanticField(
        default=False,
        description="True if distance criteria present: 'à moins de 10km', 'proche de', 'nearby'",
    )
    has_quality: bool = PydanticField(
        default=False,
        description="True if quality criteria present: 'bien noté', 'meilleur', '4 étoiles', 'top rated'",
    )
    has_iteration: bool = PydanticField(
        default=False,
        description="True if for_each pattern detected: 'pour chaque', 'à chacun', 'for each'",
    )
    has_time: bool = PydanticField(
        default=False,
        description="True if time constraint present: 'demain', 'cette semaine', 'tomorrow', 'next week'",
    )
    has_count: bool = PydanticField(
        default=False,
        description="True if count limit present: 'les 3 premiers', 'maximum 5', 'top 3', 'first 5'",
    )


class QueryAnalysisOutput(BaseModel):
    """Structured output from query analysis LLM."""

    intent: str = PydanticField(description="Intent: action or conversation")
    primary_domain: str | None = PydanticField(
        default=None, description="Primary domain for the query"
    )
    secondary_domains: list[str] = PydanticField(
        default_factory=list, description="Secondary domains needed"
    )
    confidence: float = PydanticField(default=0.8, ge=0.0, le=1.0, description="Confidence score")
    english_query: str = PydanticField(description="Query translated to English")
    resolved_references: list[ResolvedReference] = PydanticField(
        default_factory=list, description="Resolved references from context"
    )
    reasoning: str = PydanticField(description="Brief reasoning (max 20 words)")
    # Validation hints for semantic validator (v3.1 - LLM-based detection)
    is_mutation_intent: bool = PydanticField(
        default=False,
        description="True if user wants to create/update/delete/send something (mutation action)",
    )
    has_cardinality_risk: bool = PydanticField(
        default=False,
        description="True if query involves 'all/every/each/entire' - risky bulk operations",
    )

    # FOR_EACH pattern detection (plan_planner.md Section 14.2)
    for_each_detected: bool = PydanticField(
        default=False,
        description="True if user wants action for EACH result (iteration pattern). "
        "E.g., 'pour chaque hôtel, trouve les restaurants', 'envoie un email à tous mes contacts'",
    )
    for_each_collection_key: str | None = PydanticField(
        default=None,
        description="Collection key to iterate over: 'contacts', 'events', 'places', 'emails', etc.",
    )
    cardinality_magnitude: int | None = PydanticField(
        default=None,
        description="Explicit cardinality: 2-3 → 3, 'tous' → 999, 'quelques' → 5. None if unknown.",
    )
    constraint_hints: ConstraintHints = PydanticField(
        default_factory=ConstraintHints,
        description="Detected constraints for filtering results",
    )

    # Knowledge Enrichment (Brave Search)
    encyclopedia_keywords: list[str] = PydanticField(
        default_factory=list,
        description="1-3 Wikipedia-style keywords for Brave Search enrichment. "
        "Extract specific entity names, concepts, technical terms from user's ORIGINAL query language. "
        "E.g., 'Relativité générale' (FR), 'Machine learning' (EN).",
    )
    is_news_query: bool = PydanticField(
        default=False,
        description="True if query explicitly asks for news, current events, or recent updates. "
        "Keywords: 'actualités', 'dernières nouvelles', 'aujourd'hui', 'cette semaine', "
        "'what's new', 'latest', 'recent', 'breaking news'.",
    )
    is_app_help_query: bool = PydanticField(
        default=False,
        description="True if user asks about the AI assistant itself, its features, capabilities, "
        "or usage. Examples: 'What can you do?', 'How do I connect my calendar?', "
        "'Comment utiliser les rappels ?', 'Help me with settings'. "
        "NOT for general knowledge questions, only about THIS application.",
    )


# =============================================================================
# META-DOMAIN DEDUPLICATION
# =============================================================================


def _deduplicate_meta_domains(domains: list[str]) -> list[str]:
    """Remove domains that are already aggregated by a meta-domain.

    When web_search (a meta-domain) is present, its constituent domains
    (brave, perplexity, wikipedia) are removed to prevent redundant tool calls.

    Uses DOMAIN_REGISTRY metadata.aggregates to determine relationships.

    Example:
        ["web_search", "brave", "perplexity"] -> ["web_search"]
        ["brave", "perplexity"] -> ["brave", "perplexity"]  # no meta-domain, no change
    """
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    # Collect all domains aggregated by present meta-domains
    aggregated: set[str] = set()
    for domain in domains:
        config = DOMAIN_REGISTRY.get(domain)
        if config and config.metadata.get("is_meta_domain"):
            aggregated.update(config.metadata.get("aggregates", []))

    if not aggregated:
        return domains

    # Filter out aggregated domains, preserving order
    return [d for d in domains if d not in aggregated]


# =============================================================================
# RESULT DATACLASS
# =============================================================================


@dataclass
class QueryAnalysisResult:
    """Result of LLM-based query analysis."""

    intent: str  # "action" or "conversation"
    primary_domain: str | None
    secondary_domains: list[str]
    confidence: float
    english_query: str
    resolved_references: list[dict[str, str]]
    reasoning: str
    # Validation hints (v3.1 - LLM-based detection, replaces hardcoded patterns)
    is_mutation_intent: bool = False  # User wants to create/update/delete/send
    has_cardinality_risk: bool = False  # Query involves "all/every/each/entire"
    # FOR_EACH pattern detection (plan_planner.md)
    for_each_detected: bool = False  # User wants action for EACH result
    for_each_collection_key: str | None = None  # "contacts", "events", "places"
    cardinality_magnitude: int | None = None  # 999=all, N=specific, None=unknown
    constraint_hints: dict[str, bool] = field(default_factory=dict)
    # Knowledge Enrichment (Brave Search)
    encyclopedia_keywords: list[str] = field(default_factory=list)
    is_news_query: bool = False
    # App self-knowledge
    is_app_help_query: bool = False
    raw_output: dict[str, Any] = field(default_factory=dict)

    @property
    def domains(self) -> list[str]:
        """Get all domains (primary + secondary), deduplicated and order-preserved.

        Handles:
        - Simple duplicates: LLM may return primary_domain in secondary_domains too
        - Meta-domain deduplication: web_search aggregates brave/perplexity/wikipedia
        """
        all_domains = (
            [self.primary_domain] + self.secondary_domains
            if self.primary_domain
            else list(self.secondary_domains)
        )
        # Deduplicate while preserving order (primary first)
        seen: set[str] = set()
        unique_domains: list[str] = []
        for d in all_domains:
            if d not in seen:
                seen.add(d)
                unique_domains.append(d)
        return _deduplicate_meta_domains(unique_domains)

    @property
    def is_action(self) -> bool:
        """Check if intent is action."""
        return self.intent == "action"

    @property
    def is_conversation(self) -> bool:
        """Check if intent is conversation."""
        return self.intent == "conversation"

    @property
    def needs_planner(self) -> bool:
        """Check if query should go to planner."""
        return self.is_action and bool(self.domains)

    @property
    def requires_validation(self) -> bool:
        """Check if plan should trigger semantic validation (LLM-detected risk)."""
        return self.is_mutation_intent or self.has_cardinality_risk


# =============================================================================
# MAIN ANALYSIS FUNCTION
# =============================================================================


def _build_available_domains() -> list[dict[str, str]]:
    """Build the list of available domains for the query analyzer prompt.

    Includes routable domains enriched with semantic types, plus admin and user MCP
    per-server domains (filtered by user preferences).

    Returns:
        List of dicts with 'name' and 'description' keys.
    """
    from src.core.context import admin_mcp_disabled_ctx, user_mcp_tools_ctx
    from src.domains.agents.registry.domain_taxonomy import (
        DOMAIN_REGISTRY,
        collect_all_mcp_domains,
        get_routable_domains,
    )
    from src.domains.agents.semantic.expansion_service import get_expansion_service
    from src.infrastructure.mcp.registration import get_admin_mcp_domains

    expansion_service = get_expansion_service()
    available_domains: list[dict[str, str]] = []

    for domain_name in get_routable_domains():
        config = DOMAIN_REGISTRY.get(domain_name)
        if config:
            semantic_types = expansion_service.get_types_for_domain(domain_name)
            description = config.description
            if semantic_types:
                user_facing_types = [
                    t
                    for t in semantic_types
                    if not t.endswith("_id") and t not in ("Identifier", "Intangible")
                ]
                if user_facing_types:
                    description += f" (provides: {', '.join(sorted(user_facing_types)[:6])})"
            available_domains.append({"name": domain_name, "description": description})

    # F2.2+F2.5: Unified MCP per-server domain injection (admin + user).
    mcp_domains = collect_all_mcp_domains(
        admin_domains=get_admin_mcp_domains(),
        admin_disabled=admin_mcp_disabled_ctx.get(),
        user_ctx=user_mcp_tools_ctx.get(),
    )
    if mcp_domains:
        available_domains = [d for d in available_domains if d["name"] != "mcp"]
        available_domains.extend(mcp_domains)

    return available_domains


async def analyze_query(
    query: str,
    available_domains: list[dict[str, str]] | None = None,
    memory_facts: list[str] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    user_location: dict[str, Any] | None = None,
    window_size: int = 5,
    base_config: RunnableConfig | None = None,
) -> QueryAnalysisResult:
    """
    Analyze user query using LLM to detect intent and domains.

    This replaces embeddings-based SemanticDomainSelector with LLM intelligence.
    The LLM considers context (memory, history, location) to make better decisions.

    Args:
        query: User query in any language
        available_domains: List of domain dicts with name and description
        memory_facts: List of memory facts about the user
        conversation_history: Recent conversation turns
        user_location: User's current location (lat, lng, address)
        window_size: Number of history turns to include
        base_config: Parent RunnableConfig for callback preservation

    Returns:
        QueryAnalysisResult with intent, domains, and resolved references

    Example:
        >>> result = await analyze_query(
        ...     query="Quel temps chez mon frère ?",
        ...     memory_facts=["frère = jean, Lyon"],
        ... )
        >>> result.primary_domain
        "weather"
        >>> result.secondary_domains
        ["contact"]
    """
    from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
    from src.core.time_utils import get_current_datetime_context
    from src.domains.agents.prompts.prompt_loader import load_prompt
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    try:
        # Load prompt template
        prompt_template = load_prompt("query_analyzer_prompt", version="v1")

        # Build available domains string enriched with semantic types
        if available_domains is None:
            available_domains = _build_available_domains()

        domains_str = "\n".join(f"- **{d['name']}**: {d['description']}" for d in available_domains)

        # Build memory facts string
        memory_str = "None" if not memory_facts else "\n".join(f"- {fact}" for fact in memory_facts)

        # Build conversation history string
        history_str = "None"
        if conversation_history:
            history_lines = []
            for turn in conversation_history[-window_size:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")[:200]
                history_lines.append(f"[{role}]: {content}")
            history_str = "\n".join(history_lines)

        # Build user location string
        location_str = "Not available"
        if user_location:
            lat = user_location.get("lat") or user_location.get("latitude")
            lng = user_location.get("lng") or user_location.get("longitude")
            address = user_location.get("address", "")
            if lat and lng:
                location_str = f"Lat: {lat}, Lng: {lng}"
                if address:
                    location_str += f" ({address})"

        # Extract user timezone and language from config (critical for correct date calculations)
        configurable = (base_config or {}).get("configurable", {})
        user_timezone = configurable.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE)
        user_language = configurable.get("user_language", settings.default_language)

        # Format prompt - double braces in template become single braces in output
        # Use user's timezone for datetime context so LLM calculates dates correctly
        prompt = prompt_template.format(
            current_datetime=get_current_datetime_context(user_timezone, user_language),
            available_domains=domains_str,
            memory_facts=memory_str,
            conversation_history=history_str,
            user_location=location_str,
            window_size=window_size,
            user_query=query,
        )

        # Enrich config for token tracking
        config = enrich_config_with_node_metadata(base_config or {}, "query_analyzer")

        # Call LLM with structured output
        llm = get_llm("query_analyzer")
        llm_with_structure = llm.with_structured_output(QueryAnalysisOutput)

        result: QueryAnalysisOutput = await llm_with_structure.ainvoke(prompt, config=config)  # type: ignore

        logger.info(
            "query_analysis_complete",
            query_preview=query[:50],
            intent=result.intent,
            primary_domain=result.primary_domain,
            secondary_domains=result.secondary_domains,
            confidence=round(result.confidence, 2),
            reasoning=result.reasoning[:50],
            is_mutation_intent=result.is_mutation_intent,
            has_cardinality_risk=result.has_cardinality_risk,
        )

        # Validate LLM domains against available_domains.
        # The LLM may hallucinate or return domains not in the provided list
        # (e.g., disabled MCP servers). Strip them to enforce activation rules.
        available_domain_names = {d["name"] for d in available_domains}
        if result.primary_domain and result.primary_domain not in available_domain_names:
            logger.warning(
                "domain_not_available_stripped",
                domain=result.primary_domain,
                available_count=len(available_domain_names),
            )
            result.primary_domain = None
        invalid_secondary = [d for d in result.secondary_domains if d not in available_domain_names]
        if invalid_secondary:
            logger.warning(
                "domain_not_available_stripped",
                domains=invalid_secondary,
            )
            result.secondary_domains = [
                d for d in result.secondary_domains if d in available_domain_names
            ]

        return QueryAnalysisResult(
            intent=result.intent,
            primary_domain=result.primary_domain,
            secondary_domains=result.secondary_domains,
            confidence=result.confidence,
            english_query=result.english_query,
            resolved_references=[
                {"original": r.original, "resolved": r.resolved, "type": r.type}
                for r in result.resolved_references
            ],
            reasoning=result.reasoning,
            is_mutation_intent=result.is_mutation_intent,
            has_cardinality_risk=result.has_cardinality_risk,
            # FOR_EACH pattern detection
            for_each_detected=result.for_each_detected,
            for_each_collection_key=result.for_each_collection_key,
            cardinality_magnitude=result.cardinality_magnitude,
            constraint_hints=result.constraint_hints.model_dump(),  # Convert Pydantic to dict
            # Knowledge Enrichment (Brave Search)
            encyclopedia_keywords=result.encyclopedia_keywords,
            is_news_query=result.is_news_query,
            is_app_help_query=result.is_app_help_query,
            raw_output=result.model_dump(),
        )

    except Exception as e:
        logger.error(
            "query_analysis_failed",
            error=str(e),
            query_preview=query[:50],
        )
        # Fallback: return action with no domains (will go to chat)
        return QueryAnalysisResult(
            intent="conversation",
            primary_domain=None,
            secondary_domains=[],
            confidence=0.0,
            english_query=query,
            resolved_references=[],
            reasoning=f"Analysis failed: {str(e)[:30]}",
            raw_output={"error": str(e)},
        )


# =============================================================================
# SERVICE CLASS
# =============================================================================


class QueryAnalyzerService:
    """
    Unified query analysis service.

    Architecture v3.2 (Refactored) - Composition over Inheritance:
    - Composes 3 specialized services for SRP/SoC compliance
    - MemoryResolver: Memory facts + reference resolution
    - GoalInferrer: User goal inference
    - RoutingDecider: Routing decision logic
    - Uses existing ContextResolutionService (already follows SRP)

    Single entry point: analyze_full() → QueryIntelligence
    """

    def __init__(
        self,
        memory_resolver: MemoryResolver,
        context_resolver: ContextResolutionService,
        goal_inferrer: GoalInferrer,
        routing_decider: RoutingDecider,
        thresholds: V3RoutingConfig,
    ):
        """
        Initialize QueryAnalyzerService with composed services.

        Args:
            memory_resolver: Service for memory facts + reference resolution
            context_resolver: Service for context resolution from Store
            goal_inferrer: Service for user goal inference
            routing_decider: Service for routing decisions
            thresholds: Configuration for routing thresholds
        """
        self.memory_resolver = memory_resolver
        self.context_resolver = context_resolver
        self.goal_inferrer = goal_inferrer
        self.routing_decider = routing_decider
        self.thresholds = thresholds

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def analyze(
        self,
        query: str,
        available_domains: list[dict[str, str]] | None = None,
        memory_facts: list[str] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        user_location: dict[str, Any] | None = None,
        window_size: int = 5,
        base_config: RunnableConfig | None = None,
    ) -> QueryAnalysisResult:
        """
        Simple LLM analysis (backward compatible).

        See analyze_query() for full documentation.
        """
        return await analyze_query(
            query=query,
            available_domains=available_domains,
            memory_facts=memory_facts,
            conversation_history=conversation_history,
            user_location=user_location,
            window_size=window_size,
            base_config=base_config,
        )

    async def analyze_full(
        self,
        query: str,
        messages: list[BaseMessage],
        state: dict[str, Any],
        config: RunnableConfig,
        *,
        original_query: str | None = None,
    ) -> QueryIntelligence:
        """
        Complete analysis with routing decision.

        Replaces QueryIntelligenceService.analyze().

        Flow:
        1. Memory facts retrieval (internalized)
        2. LLM Analysis (single call)
        3. Semantic Domain Expansion (if person reference)
        4. Chat Override (if conversation intent)
        5. Context Resolution
        6. User Goal inference (fast pattern matching)
        7. Routing Decision

        Error handling:
        - LLM failure → fallback chat route
        - Memory failure → continue without memory
        - Context failure → continue without context

        Args:
            query: User query text (English for domain detection via semantic pivot)
            messages: Conversation messages
            state: Agent state dict
            config: RunnableConfig for callbacks
            original_query: Original user query in their language (for debug panel display).
                          If not provided, defaults to `query`.

        Returns:
            QueryIntelligence with full analysis and routing decision
        """
        from src.core.field_names import FIELD_RUN_ID

        reasoning_trace: list[str] = []
        intelligent_mechanisms: dict[str, Any] = {}

        configurable = config.get("configurable", {})
        run_id = configurable.get(FIELD_RUN_ID, "unknown")
        user_language = state.get("user_language", settings.default_language)

        try:
            # === STEP 1: Memory facts retrieval + reference resolution ===
            # Delegated to MemoryResolver (SRP: single service for memory operations)
            user_id = configurable.get("langgraph_user_id")
            if not user_id or not isinstance(user_id, str):
                user_id = ""  # Fallback to empty string for memory resolver
            memory_facts, memory_resolved = await self.memory_resolver.retrieve_and_resolve(
                query=query,
                user_id=user_id,
                config=config,
            )

            # Extract resolved references and enriched query
            memory_resolved_refs: dict[str, str] = {}
            memory_enriched_query: str | None = None

            if memory_resolved and memory_resolved.mappings:
                memory_resolved_refs = memory_resolved.mappings
                memory_enriched_query = memory_resolved.enriched_query
                logger.info(
                    "memory_reference_resolution_applied",
                    mappings=memory_resolved_refs,
                    enriched_query_preview=(
                        memory_enriched_query[:50] if memory_enriched_query else None
                    ),
                    query_preview=query[:50],
                )

            # Get conversation history and user location from state
            conversation_history = self._extract_conversation_history(messages)
            user_location = state.get("user_location")

            # === STEP 2: LLM Analysis ===
            # Build available_domains once — passed to analyze() for prompt construction
            # AND used post-expansion for domain validation (prevents re-introduction
            # of disabled domains via semantic expansion).
            available_domains = _build_available_domains()

            analysis_result = await self.analyze(
                query=query,
                available_domains=available_domains,
                memory_facts=memory_facts,
                conversation_history=conversation_history,
                user_location=user_location,
                base_config=config,
            )

            # FIX 2026-02-06: Apply FOR_EACH heuristics post-processing
            # Enhance detection for implicit patterns the LLM may miss
            analysis_result = _apply_for_each_heuristics(
                analysis_result,
                query.lower(),
                analysis_result.domains,
            )

            # Extract results
            english_query = analysis_result.english_query
            intent = analysis_result.intent
            domains = analysis_result.domains
            confidence = analysis_result.confidence

            # Map LLM intent to internal granular intents (use english_query for consistent matching)
            immediate_intent = self._map_llm_intent_to_internal(intent, english_query, domains)

            reasoning_trace.append(f"LLM Analysis: intent={intent}, domains={domains}")
            reasoning_trace.append(f"English: '{english_query[:50]}...'")
            reasoning_trace.append(f"Confidence: {confidence:.2f}")

            # Track for debug panel
            intelligent_mechanisms["llm_query_analysis"] = {
                "applied": True,
                "intent": intent,
                "mapped_intent": immediate_intent,
                "primary_domain": analysis_result.primary_domain,
                "secondary_domains": analysis_result.secondary_domains,
                "confidence": confidence,
                "english_query": english_query,
                "reasoning": analysis_result.reasoning,
            }

            # Handle resolved references: merge memory service + LLM results
            # Memory service has priority (dedicated, more accurate)
            resolved_refs_dict: dict[str, str] | None = None

            # Start with memory service results (higher priority)
            if memory_resolved_refs:
                resolved_refs_dict = dict(memory_resolved_refs)
                intelligent_mechanisms["memory_resolution_service"] = {
                    "applied": True,
                    "source": "MemoryReferenceResolutionService",
                    "mappings": memory_resolved_refs,
                }
                reasoning_trace.append(f"Memory resolved: {list(memory_resolved_refs.keys())}")

            # Add LLM references (lower priority, don't overwrite memory service)
            if analysis_result.resolved_references:
                llm_refs = {
                    ref["original"]: ref["resolved"] for ref in analysis_result.resolved_references
                }
                if resolved_refs_dict is None:
                    resolved_refs_dict = llm_refs
                else:
                    # Only add LLM refs that aren't already resolved by memory service
                    for orig, resolved in llm_refs.items():
                        if orig not in resolved_refs_dict:
                            resolved_refs_dict[orig] = resolved

                intelligent_mechanisms["memory_resolution_llm"] = {
                    "applied": True,
                    "source": "QueryAnalyzer LLM",
                    "resolved_references": analysis_result.resolved_references,
                    "num_references": len(analysis_result.resolved_references),
                }
                reasoning_trace.append(f"LLM resolved: {list(llm_refs.keys())}")

            # === STEP 3: Semantic Type Domain Expansion ===
            has_person_reference = (
                any(ref.get("type") == "person" for ref in analysis_result.resolved_references)
                if analysis_result.resolved_references
                else False
            )
            expansion_reasons: list[str] = []
            original_domains = list(domains)

            if domains:
                expanded_domains = await self._expand_domains_for_semantic_types(
                    domains=domains,
                    has_person_reference=has_person_reference,
                    reasoning_trace=reasoning_trace,
                    all_scores=dict.fromkeys(domains, 0.8),
                    expansion_reasons=expansion_reasons,
                )
                if expanded_domains != domains:
                    # Validate expanded domains against available_domains to prevent
                    # semantic expansion from re-introducing disabled domains.
                    available_names = {d["name"] for d in available_domains}
                    valid_expanded = [d for d in expanded_domains if d in available_names]
                    stripped_by_validation = [
                        d for d in expanded_domains if d not in available_names
                    ]
                    if stripped_by_validation:
                        logger.warning(
                            "expansion_domain_not_available_stripped",
                            domains=stripped_by_validation,
                        )
                    domains = valid_expanded
                    reasoning_trace.append(f"Semantic expansion: {valid_expanded}")
                    intelligent_mechanisms["semantic_expansion"] = {
                        "applied": True,
                        "original_domains": original_domains,
                        "expanded_domains": list(valid_expanded),
                        "added_domains": [d for d in valid_expanded if d not in original_domains],
                        "reasons": expansion_reasons,
                        "has_person_reference": has_person_reference,
                    }

            # === STEP 4: Chat Override ===
            # Research-only domains that should NOT be cleared even if intent is "conversation"
            # These domains only fetch information and don't perform mutations
            # "search for information about X" is often misclassified as conversation
            from src.domains.agents.registry.domain_taxonomy import is_mcp_domain

            RESEARCH_ONLY_DOMAINS = {"wikipedia", "perplexity", "web_search", "brave"}

            if intent == "conversation" and confidence >= self.thresholds.chat_override_threshold:
                original_domains_before_override = list(domains)

                # Check if all domains are research-only (includes per-server MCP domains)
                has_only_research_domains = domains and all(
                    d in RESEARCH_ONLY_DOMAINS or is_mcp_domain(d) for d in domains
                )

                if has_only_research_domains:
                    # Keep research domains - likely a misclassified search request
                    logger.info(
                        "chat_override_skipped_research_domains",
                        domains=domains,
                        intent=intent,
                        confidence=confidence,
                        reason="Research-only domains kept despite conversation intent",
                    )
                    reasoning_trace.append(
                        f"Chat Override SKIPPED: research-only domains kept ({domains})"
                    )
                    intelligent_mechanisms["chat_override"] = {
                        "applied": False,
                        "original_domains": original_domains_before_override,
                        "intent": intent,
                        "confidence": confidence,
                        "override_threshold": self.thresholds.chat_override_threshold,
                        "reason": "Research-only domains preserved",
                    }
                else:
                    # Clear domains as usual
                    logger.info(
                        "chat_override_applied",
                        original_domains=original_domains_before_override,
                        intent=intent,
                        confidence=confidence,
                        reason="LLM classified as conversation",
                    )
                    domains = []
                    reasoning_trace.append(
                        f"Chat Override: domains cleared (conversation intent, conf={confidence:.2f})"
                    )
                    intelligent_mechanisms["chat_override"] = {
                        "applied": True,
                        "original_domains": original_domains_before_override,
                        "intent": intent,
                        "confidence": confidence,
                        "override_threshold": self.thresholds.chat_override_threshold,
                        "reason": "LLM classified as conversation",
                    }

            # === STEP 5: Context Resolution ===
            context_result, _ = await self.context_resolver.resolve_context(
                query=query,
                state=state,  # type: ignore
                config=config,
                run_id=run_id,
                english_query=english_query,
            )
            turn_type = self._determine_turn_type(context_result, immediate_intent)

            # === STEP 6: Set english_enriched_query ===
            english_enriched_query: str | None = english_query if resolved_refs_dict else None

            # === STEP 7: User Goal Inference ===
            # Delegated to GoalInferrer (SRP: single service for goal inference)
            user_goal, goal_reasoning = self.goal_inferrer.infer(
                query=query,
                intent=immediate_intent,
                domains=domains,
                messages=messages,
            )
            reasoning_trace.append(f"Goal: {user_goal.value} ({goal_reasoning})")

            # === STEP 8: Domain Selection for References ===
            source_domain = None
            if context_result and context_result.items:
                source_domain = context_result.source_domain
                if source_domain:
                    if turn_type == "REFERENCE_PURE":
                        domains = [source_domain]
                        reasoning_trace.append(f"REFERENCE_PURE with context → [{source_domain}]")
                    elif source_domain not in domains:
                        domains = domains + [source_domain]
                        reasoning_trace.append(
                            f"REFERENCE_ACTION: {domains} (source={source_domain})"
                        )

            # === STEP 9: Semantic Fallback Check ===
            if SemanticFallback.should_fallback(confidence):
                reasoning_trace.append(f"Low confidence ({confidence:.2f}) - Semantic Fallback")

            # === STEP 10: Routing Decision ===
            # Delegated to RoutingDecider (SRP: single service for routing logic)
            route_to, final_confidence, bypass = self.routing_decider.decide(
                intent=immediate_intent,
                intent_confidence=confidence,
                domains=domains,
                semantic_score=confidence,
                is_app_help_query=analysis_result.is_app_help_query,
            )

            # Build domain scores with softmax calibration
            # FIX 2026-02-06: Apply softmax calibration for discriminated domain scores
            # This allows downstream services to know which domain is primary vs secondary
            primary = domains[0] if domains else None
            secondary = domains[1:] if len(domains) > 1 else []
            domain_calibrated = _apply_domain_softmax_calibration(
                primary,
                secondary,
                confidence,
            )

            # Keep raw scores for backward compatibility
            domain_scores = dict.fromkeys(domains, confidence) if domains else {}

            # Use original_query if provided, else fall back to query
            # This ensures the user's actual query (in their language) is preserved for debug panel
            actual_original_query = original_query if original_query is not None else query

            return QueryIntelligence(
                original_query=actual_original_query,
                english_query=english_query,
                english_enriched_query=english_enriched_query,
                immediate_intent=immediate_intent,
                immediate_confidence=confidence,
                user_goal=user_goal,
                goal_reasoning=goal_reasoning,
                implicit_intents=[],  # Removed - was dead code
                domains=domains,
                primary_domain=domains[0] if domains else "general",
                domain_scores=domain_scores,
                domain_calibrated_scores=domain_calibrated,
                turn_type=turn_type,
                resolved_context=(
                    context_result if context_result and context_result.items else None
                ),
                source_turn_id=context_result.source_turn_id if context_result else None,
                source_domain=source_domain,
                resolved_references=resolved_refs_dict,
                anticipated_needs=[],  # Removed - was dead code
                fallback_strategies=[],  # Removed - was dead code
                suggested_enrichments=[],  # Removed - was dead code
                route_to=route_to,
                bypass_llm=bypass,
                confidence=final_confidence,
                user_language=user_language,
                reasoning_trace=reasoning_trace,
                intelligent_mechanisms=intelligent_mechanisms,
                is_mutation_intent=analysis_result.is_mutation_intent,
                has_cardinality_risk=analysis_result.has_cardinality_risk,
                # FOR_EACH pattern detection (plan_planner.md Section 14.1)
                constraint_hints=analysis_result.constraint_hints,
                for_each_detected=analysis_result.for_each_detected,
                for_each_collection_key=analysis_result.for_each_collection_key,
                cardinality_magnitude=analysis_result.cardinality_magnitude,
                cardinality_mode="each" if analysis_result.for_each_detected else "single",
                # Knowledge Enrichment (Brave Search)
                encyclopedia_keywords=analysis_result.encyclopedia_keywords,
                is_news_query=analysis_result.is_news_query,
                # App self-knowledge
                is_app_help_query=analysis_result.is_app_help_query,
            )

        except Exception as e:
            # Use original_query for fallback (user's actual input, not English translation)
            fallback_query = original_query if original_query is not None else query
            logger.error(
                "analyze_full_failed",
                error=str(e),
                query_preview=fallback_query[:50],
                run_id=run_id,
            )
            return self._create_fallback_intelligence(fallback_query, user_language, error=e)

    # =========================================================================
    # PRIVATE METHODS (migrated from QueryIntelligenceService)
    # =========================================================================

    def _extract_conversation_history(
        self,
        messages: list[BaseMessage],
        window_size: int = 5,
    ) -> list[dict[str, str]]:
        """Extract conversation history for LLM context."""
        history = []
        for msg in messages[-window_size * 2 :]:
            role = "user" if msg.type == "human" else "assistant"
            content = str(msg.content) if hasattr(msg, "content") else ""
            if content:
                history.append({"role": role, "content": content[:500]})
        return history

    def _map_llm_intent_to_internal(
        self,
        llm_intent: str,
        english_query: str,
        domains: list[str],
    ) -> str:
        """
        Map LLM intent ("action" or "conversation") to internal granular intents.

        Uses english_query (from semantic pivot) for consistent pattern matching.
        Patterns are centralized in core.constants (INTENT_PATTERNS_*).

        Returns: search, create, update, delete, send, chat, list
        """
        if llm_intent == "conversation":
            return "chat"

        query_lower = english_query.lower()

        # Mutation patterns (in priority order) - English only via semantic pivot
        if any(w in query_lower for w in INTENT_PATTERNS_SEND):
            if "email" in domains:
                return "send"

        if any(w in query_lower for w in INTENT_PATTERNS_DELETE):
            return "delete"

        if any(w in query_lower for w in INTENT_PATTERNS_CREATE):
            return "create"

        if any(w in query_lower for w in INTENT_PATTERNS_UPDATE):
            return "update"

        return "search"

    def _determine_turn_type(self, context_result: ResolvedContext | None, intent: str) -> str:
        """Determine the turn type based on context and intent."""
        if not context_result or not context_result.items:
            return "ACTION"

        ACTION_INTENTS = {"send", "create", "update", "delete"}
        if intent in ACTION_INTENTS:
            return "REFERENCE_ACTION"
        return "REFERENCE_PURE"

    async def _expand_domains_for_semantic_types(
        self,
        domains: list[str],
        has_person_reference: bool,
        reasoning_trace: list[str],
        all_scores: dict[str, float] | None = None,
        expansion_reasons: list[str] | None = None,
    ) -> list[str]:
        """
        Expand domains based on semantic type requirements.

        Example: "trajet chez mon frère" → routes + memory("mon frère") → add contacts
        """
        if not domains:
            return domains

        try:
            from src.domains.agents.registry.agent_registry import get_global_registry
            from src.domains.agents.semantic.expansion_service import get_expansion_service

            agent_registry = get_global_registry()
            required_types = agent_registry.get_required_semantic_types_for_domains(domains)

            if not required_types:
                return domains

            required_type_names = set(required_types.keys())
            expansion_service = get_expansion_service()

            expanded_domains = await expansion_service.expand_domains_iso_functional(
                domains=domains,
                has_person_reference=has_person_reference,
                required_semantic_types=required_type_names,
                query="",
            )

            # Build reasons list for logging
            reasons = expansion_reasons if expansion_reasons is not None else []
            added_domains = [d for d in expanded_domains if d not in domains]

            if added_domains:
                for added_domain in added_domains:
                    provided_types = []
                    for sem_type in required_type_names:
                        providers = expansion_service.get_providers_for_type(sem_type)
                        if added_domain in providers and sem_type in (
                            "physical_address",
                            "email_address",
                        ):
                            provided_types.append(sem_type)

                    if provided_types:
                        reasons.append(
                            f"{added_domain} (provides {', '.join(provided_types)} for person reference)"
                        )

                logger.info(
                    "semantic_type_domain_expansion",
                    original_domains=domains,
                    expanded_domains=expanded_domains,
                    added_domains=added_domains,
                    reasons=reasons,
                    has_person_reference=has_person_reference,
                )
                reasoning_trace.append(f"Semantic type expansion: +{reasons}")

            return expanded_domains

        except Exception as e:
            logger.warning(
                "semantic_type_expansion_failed",
                error=str(e),
                domains=domains,
            )
            return domains

    def _create_fallback_intelligence(
        self,
        query: str,
        user_language: str = settings.default_language,
        error: Exception | None = None,
    ) -> QueryIntelligence:
        """Create minimal QueryIntelligence on error - routes to chat."""
        return QueryIntelligence(
            original_query=query,
            english_query=query,
            english_enriched_query=None,
            immediate_intent="chat",
            immediate_confidence=0.0,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="Fallback due to analysis failure",
            implicit_intents=[],
            domains=[],
            primary_domain="general",
            domain_scores={},
            domain_calibrated_scores={},
            turn_type="INITIAL",
            resolved_context=None,
            source_turn_id=None,
            source_domain=None,
            resolved_references=None,
            anticipated_needs=[],
            fallback_strategies=[],
            suggested_enrichments=[],
            route_to="response",
            bypass_llm=False,
            confidence=0.0,
            user_language=user_language,
            reasoning_trace=[f"Analysis failed: {str(error)[:50]}" if error else "Fallback"],
            intelligent_mechanisms={"error": {"message": str(error)}} if error else {},
            # FOR_EACH pattern detection - defaults for fallback
            constraint_hints={},
            for_each_detected=False,
            for_each_collection_key=None,
            cardinality_magnitude=None,
            cardinality_mode="single",
            # Knowledge Enrichment - defaults for fallback
            encyclopedia_keywords=[],
            is_news_query=False,
            # App self-knowledge - defaults for fallback
            is_app_help_query=False,
        )


# =============================================================================
# SINGLETON
# =============================================================================

_service: QueryAnalyzerService | None = None


def get_query_analyzer_service() -> QueryAnalyzerService:
    """
    Get singleton QueryAnalyzerService instance.

    Lazy-initializes dependencies via composition pattern:
    - MemoryResolver for memory facts retrieval and reference resolution
    - ContextResolutionService for context resolution
    - GoalInferrer for user goal inference
    - RoutingDecider for routing decision logic
    - Routing thresholds configuration
    """
    global _service
    if _service is None:
        from src.core.config.agents import get_routing_thresholds
        from src.domains.agents.services.analysis import (
            get_goal_inferrer,
            get_memory_resolver,
            get_routing_decider,
        )
        from src.domains.agents.services.context_resolution_service import (
            get_context_resolution_service,
        )

        _service = QueryAnalyzerService(
            memory_resolver=get_memory_resolver(),
            context_resolver=get_context_resolution_service(),
            goal_inferrer=get_goal_inferrer(),
            routing_decider=get_routing_decider(),
            thresholds=get_routing_thresholds(),
        )
    return _service


def reset_query_analyzer_service() -> None:
    """Reset singleton (for testing)."""
    global _service
    _service = None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "QueryAnalysisResult",
    "QueryAnalysisOutput",
    "QueryAnalyzerService",
    "analyze_query",
    "get_query_analyzer_service",
    "reset_query_analyzer_service",
]
