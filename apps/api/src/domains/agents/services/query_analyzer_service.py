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

import asyncio
import functools
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np
from langchain_core.messages import BaseMessage

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
from src.domains.agents.context.runtime_context import (
    runtime_language,
    runtime_timezone,
    runtime_user_id_str,
)
from src.domains.agents.services.analysis.domain_availability import build_available_domains
from src.domains.agents.services.analysis.peer_directory import (
    apply_peer_domain_correction,
    detect_mentioned_peers,
    format_peer_directory,
    load_connected_peer_names,
)
from src.domains.agents.services.analysis.skill_suppression import (
    _is_dialogue_skill,
    effective_skill_name,
)
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    planner_semantic_filter_terms_emitted,
)

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

# Word-boundary matching is mandatory: substring matching made "call my wife"
# trigger FOR_EACH via the embedded "all my" (c[all my] wife) — every natural
# "call my X" telephony request was rejected by the semantic validator.
_FOR_EACH_EXPLICIT_RE: re.Pattern[str] = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in sorted(_FOR_EACH_PATTERNS_EXPLICIT)) + r")\b"
)


@functools.lru_cache(maxsize=1)
def _get_plural_hints_regex() -> re.Pattern[str]:
    """Word-boundary regex over the plural collection hints (same rationale)."""
    hints = "|".join(re.escape(h) for h in sorted(_get_plural_collection_hints()))
    return re.compile(r"\b(?:" + hints + r")\b")


@functools.lru_cache(maxsize=1)
def _get_plural_collection_hints() -> frozenset[str]:
    """Derive plural collection nouns from DOMAIN_REGISTRY result_keys.

    Uses the canonical source (domain_taxonomy.DOMAIN_REGISTRY) to avoid
    maintaining a hardcoded list that drifts when new domains are added.

    Cached because DOMAIN_REGISTRY is static and this is called per query.

    Returns:
        Frozenset of result_key values (e.g., "contacts", "emails", "events").
    """
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    return frozenset(config.result_key for config in DOMAIN_REGISTRY.values() if config.is_routable)


def _get_collection_key_for_domain(domain: str) -> str | None:
    """Get the collection key (result_key) for a domain from DOMAIN_REGISTRY.

    Uses the canonical source instead of a hardcoded mapping.

    Args:
        domain: Domain name (e.g., "contact", "email").

    Returns:
        The result_key (e.g., "contacts", "emails") or None if not found.
    """
    from src.domains.agents.registry.domain_taxonomy import get_domain_config

    config = get_domain_config(domain)
    return config.result_key if config else None


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

    # Heuristic 1: Explicit patterns (word-bounded — see _FOR_EACH_EXPLICIT_RE)
    has_explicit = bool(_FOR_EACH_EXPLICIT_RE.search(query_lower))

    # Heuristic 2: Plural collection noun + mutation intent (word-bounded)
    has_plural = bool(_get_plural_hints_regex().search(query_lower))
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

    # Infer collection key from domains (uses DOMAIN_REGISTRY as canonical source)
    collection_key = result.for_each_collection_key
    if not collection_key:
        for domain in domains:
            key = _get_collection_key_for_domain(domain)
            if key:
                collection_key = key
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

    return replace(
        result,
        for_each_detected=True,
        for_each_collection_key=collection_key,
        has_cardinality_risk=True,
    )


# =============================================================================
# OUTPUT SCHEMA (Pydantic for structured output)
# =============================================================================
# The structured-output contract now lives in `analysis/query_analysis_schemas.py`
# (ADR-160). Re-exported here: `context_resolution_service` and the test suite
# import these names from this module, and that path must keep working.
from src.domains.agents.services.analysis.query_analysis_schemas import (  # noqa: E402
    ContextReferenceOutput,
    QueryAnalysisOutput,
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
    skill_name: str | None = None
    # Indexable vs Semantic — probabilistic hint for the planner
    semantic_filter_terms: list[str] = field(default_factory=list)
    # True when the query carries a concrete time bound (explicit date / relative
    # day / named period). False for open horizons ("upcoming", "my next 3") and
    # no-time queries — used to discard planner-hallucinated date bounds.
    has_temporal_reference: bool = False
    # Context reference (LLM-first, 2026-04)
    context_reference: ContextReferenceOutput = field(default_factory=ContextReferenceOutput)
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


# NOTE: _build_available_domains moved to analysis/domain_availability.py (the
# ratchet freezes this module at its audited size, so a growing feature pays
# for itself by extracting a cohesive concern). It stays importable from here —
# tests included — under its original private name.
_build_available_domains = build_available_domains


# NOTE: _is_dialogue_skill moved to analysis/skill_suppression.py with the
# MCP-domain guard; it stays importable from this module (top import) so
# existing importers — tests included — keep their path.


async def analyze_query(
    query: str,
    available_domains: list[dict[str, str]] | None = None,
    memory_facts: list[str] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    user_location: dict[str, Any] | None = None,
    window_size: int = 5,
    base_config: RunnableConfig | None = None,
    connected_peers: list[str] | None = None,
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
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.core.time_utils import get_current_datetime_context
    from src.domains.agents.prompts.prompt_loader import load_prompt
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.structured_output import get_structured_output

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
        (base_config or {}).get("configurable", {})
        user_timezone = runtime_timezone(DEFAULT_USER_DISPLAY_TIMEZONE)
        user_language = runtime_language()

        # Build available skills for semantic identification.
        # skill_name is declared in QueryAnalysisOutput with default=None.
        # All active skills (deterministic and non-deterministic) are exposed:
        # the LLM identifies a matching skill by description alignment, and the
        # deterministic-vs-dynamic distinction is resolved downstream (SkillBypass
        # triggers for deterministic; LLM planner handles the rest).
        skills_str = "(no skills available)"
        if getattr(settings, "skills_enabled", False):
            from src.core.context import active_skills_ctx
            from src.domains.skills.cache import SkillsCache

            _qa_user_id = runtime_user_id_str() or ""
            _qa_active = active_skills_ctx.get()
            _qa_skills = SkillsCache.get_for_user(_qa_user_id)
            _qa_visible = [
                s
                for s in _qa_skills
                if not s.get("disable_model_invocation")
                and (_qa_active is None or s["name"] in _qa_active)
            ]
            if _qa_visible:
                skills_str = "\n".join(
                    f"- **{s['name']}**: {s['description']}" for s in _qa_visible
                )

        # Format prompt - double braces in template become single braces in output
        # Use user's timezone for datetime context so LLM calculates dates correctly
        prompt = prompt_template.format(
            current_datetime=get_current_datetime_context(user_timezone, user_language),
            available_domains=domains_str,
            available_skills=skills_str,
            connected_peers=format_peer_directory(connected_peers or []),
            memory_facts=memory_str,
            conversation_history=history_str,
            user_location=location_str,
            window_size=window_size,
            user_query=query.replace("{", "{{").replace("}", "}}"),
        )

        # Call LLM with structured output (provider-agnostic via helper)
        llm = get_llm("query_analyzer")
        agent_config = get_llm_config_for_agent(settings, "query_analyzer")

        import asyncio

        from langchain_core.messages import HumanMessage

        # NO reasoning_emit here — deliberate (reasoning-streaming POC decision:
        # query_analyzer EXCLUDED). This is a fast head-of-graph classification
        # with no UX value for a live "💭" block, and streaming the buffered
        # with_structured_output path caused a silent SECOND full LLM call per
        # turn (+1.3-2.5s TTFT, double cost) before the negative-cache guard
        # existed. Keeping it off guarantees one call on every provider.
        result: QueryAnalysisOutput = await asyncio.wait_for(
            get_structured_output(
                llm=llm,
                messages=[HumanMessage(content=prompt)],
                schema=QueryAnalysisOutput,
                provider=agent_config.provider,
                node_name="query_analyzer",
                config=base_config,
            ),
            timeout=settings.query_analyzer_llm_timeout_seconds,
        )

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
            constraint_hints=result.constraint_hints.model_dump(),
            # Knowledge Enrichment (Brave Search)
            encyclopedia_keywords=result.encyclopedia_keywords,
            is_news_query=result.is_news_query,
            is_app_help_query=result.is_app_help_query,
            skill_name=result.skill_name,
            # Indexable vs Semantic — probabilistic hint for the planner
            semantic_filter_terms=[
                t.strip().lower() for t in (result.semantic_filter_terms or []) if t.strip()
            ],
            has_temporal_reference=result.has_temporal_reference,
            # Context reference (LLM-first, 2026-04)
            context_reference=result.context_reference,
            raw_output=result.model_dump(),
        )

    except Exception as e:
        logger.error(
            "query_analysis_failed",
            error=str(e),
            error_type=type(e).__name__,
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


def _update_pattern_subsumes_create(query_lower: str) -> bool:
    """True when a matched UPDATE pattern strictly CONTAINS a matched CREATE one.

    Intent detection checks CREATE before UPDATE, and the patterns are matched as
    substrings — so "reschedule" (UPDATE) was shadowed by "schedule" (CREATE) and
    its declaration was unreachable. "reschedule my meeting" was then classified
    as a creation, loading the create tools and leaving ``update_event_tool``
    out: a duplicated event instead of a moved one.

    Verified exhaustively across the four ``INTENT_PATTERNS_*`` sets: this pair
    is the only such overlap, so the rule changes nothing else.

    Args:
        query_lower: Lower-cased pivoted English query.

    Returns:
        True when the more specific UPDATE reading must win.
    """
    create_hits = [w for w in INTENT_PATTERNS_CREATE if w in query_lower]
    if not create_hits:
        return False
    update_hits = [w for w in INTENT_PATTERNS_UPDATE if w in query_lower]
    return any(create in update for create in create_hits for update in update_hits)


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
        connected_peers: list[str] | None = None,
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
            connected_peers=connected_peers,
        )

    async def analyze_full(
        self,
        query: str,
        messages: list[BaseMessage],
        state: dict[str, Any],
        config: RunnableConfig,
        *,
        original_query: str | None = None,
        english_query_task: asyncio.Task[str] | None = None,
    ) -> QueryIntelligence:
        """
        Complete analysis with routing decision.

        Replaces QueryIntelligenceService.analyze().

        Flow:
        1. Memory facts retrieval (internalized) — overlapped with the
           semantic-pivot translation when `english_query_task` is provided
           (latency lot R1, 2026-07: the two are data-independent, memory
           embeds the ORIGINAL query)
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
            query: User query text. English (semantic pivot) when the caller
                already awaited the translation; the ORIGINAL query when
                `english_query_task` is provided — the awaited task result then
                replaces it for every post-memory step, preserving the exact
                historical semantics.
            messages: Conversation messages
            state: Agent state dict
            config: RunnableConfig for callbacks
            original_query: Original user query in their language (for debug panel display).
                          If not provided, defaults to `query`.
            english_query_task: Optional in-flight semantic-pivot translation
                task, awaited concurrently with the memory-resolution phase.
                The task never raises (translate_to_english falls back to the
                original query internally); it is cancelled best-effort if this
                method fails before awaiting it.

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
            user_id = runtime_user_id_str(None)
            if not user_id or not isinstance(user_id, str):
                user_id = ""  # Fallback to empty string for memory resolver
            # Use original_query (user's language) for memory embedding search.
            # Memories are stored with embeddings in the user's language, so
            # cross-language search (English query vs French memories) yields
            # poor cosine similarity with Gemini gemini-embedding-001.
            # The English query is still used for domain detection downstream.
            memory_search_query = original_query if original_query else query
            if english_query_task is not None:
                # Latency lot R1 (2026-07): overlap the semantic-pivot LLM call
                # with the memory-resolution phase. Rebinding `query` to the
                # awaited translation reproduces exactly the historical caller
                # behaviour (router awaited the pivot, then passed it as
                # `query`) for every step below.
                memory_resolution, query = await asyncio.gather(
                    self.memory_resolver.retrieve_and_resolve(
                        query=memory_search_query,
                        user_id=user_id,
                        config=config,
                    ),
                    english_query_task,
                )
            else:
                memory_resolution = await self.memory_resolver.retrieve_and_resolve(
                    query=memory_search_query,
                    user_id=user_id,
                    config=config,
                )
            memory_facts = memory_resolution.facts
            memory_resolved = memory_resolution.resolved
            memory_extracted_references = memory_resolution.references

            # Extract resolved references and enriched query
            memory_resolved_refs: dict[str, str] = {}
            memory_enriched_query: str | None = None

            if memory_resolved and memory_resolved.mappings:
                memory_resolved_refs = memory_resolved.mappings
                memory_enriched_query = memory_resolved.enriched_query
                # No PII at INFO: mappings are resolved person names (DEBUG only).
                logger.info(
                    "memory_reference_resolution_applied",
                    mappings_count=len(memory_resolved_refs),
                )
                logger.debug(
                    "memory_reference_resolution_mappings",
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

            # Peer-routing awareness (defect 2026-07-30): the analyzer cannot
            # tell "is Jerome G free tomorrow?" from a question about the
            # user's own calendar unless it knows Jerome G is a connected USER.
            # One indexed query, flag-gated, kept sequential on purpose — it is
            # ~1 ms against a ~4 s analyzer call, and a task here would buy
            # nothing but a cancellation path to get wrong.
            connected_peers = await load_connected_peer_names(user_id)

            analysis_result = await self.analyze(
                query=query,
                available_domains=available_domains,
                memory_facts=memory_facts,
                conversation_history=conversation_history,
                user_location=user_location,
                base_config=config,
                connected_peers=connected_peers,
            )

            # Latency lot R3 (semantic_pivot_enabled=False): no pivot ran — the
            # analyzer received the original query and produced its own English
            # translation; feed it to the downstream English pattern-matching
            # steps (FOR_EACH heuristics, context resolution, goal inference).
            # No-op on the historical path where `query` already holds the
            # awaited pivot output.
            if english_query_task is None and analysis_result.english_query:
                query = analysis_result.english_query

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
            # Deterministic guarantee behind the prompt awareness above: a
            # connected user was named, yet the LLM answered with a domain that
            # reads THIS user's own data. Additive — "am I free to see Jerome"
            # legitimately needs both — so the tool selector still arbitrates.
            mentioned_peers = detect_mentioned_peers(
                [original_query, query, english_query, *(memory_resolved_refs or {}).values()],
                connected_peers,
            )
            domains = apply_peer_domain_correction(analysis_result.domains, mentioned_peers)
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
            if mentioned_peers:
                # Names are PII — the debug panel gets the count and the verdict.
                intelligent_mechanisms["peer_domain_correction"] = {
                    "applied": domains != analysis_result.domains,
                    "mentioned_count": len(mentioned_peers),
                    "domains_before": analysis_result.domains,
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
            # Person-reference evidence, most reliable source first. The memory
            # resolver pipeline targets relational references by construction
            # ("mon frère", "le voisin"), so its outputs are deterministic
            # evidence — unlike the analyzer LLM refs, which intermittently
            # omit the person typing (recurring failure: contact expansion
            # skipped → get_route receives a person name as destination).
            person_evidence_sources: list[str] = []
            if memory_resolved_refs:
                # E1: resolution produced identity mappings for this turn.
                person_evidence_sources.append("memory_mappings")
            if memory_extracted_references:
                # E2: extraction found relational references, kept even when
                # resolution failed (person exists but no memory fact). May
                # over-trigger on personal places ("mon travail") — benign:
                # expansion still requires a matching required semantic type.
                person_evidence_sources.append("memory_extraction")
            if analysis_result.resolved_references and any(
                ref.get("type") == "person" for ref in analysis_result.resolved_references
            ):
                # E3: analyzer LLM typed a resolved reference as person.
                person_evidence_sources.append("analyzer_llm")

            has_person_reference = bool(person_evidence_sources)
            if person_evidence_sources:
                logger.debug(
                    "person_reference_evidence",
                    sources=person_evidence_sources,
                    extracted_count=len(memory_extracted_references),
                    mappings_count=len(memory_resolved_refs),
                )

            # Typed evidence entities for evidence-driven expansion: a person
            # reference materializes as Contact; a context reference to a
            # previous item (event, place, contact) as that domain's entity.
            from src.domains.agents.semantic.expansion_service import (
                EVIDENCE_ENTITY_TYPE_BY_DOMAIN,
                PERSON_EVIDENCE_ENTITY,
            )

            evidence_entities: set[str] = set()
            if has_person_reference:
                evidence_entities.add(PERSON_EVIDENCE_ENTITY)
            context_ref = analysis_result.context_reference
            if context_ref and context_ref.has_reference and context_ref.reference_domain:
                referenced_entity = EVIDENCE_ENTITY_TYPE_BY_DOMAIN.get(context_ref.reference_domain)
                if referenced_entity:
                    evidence_entities.add(referenced_entity)

            expansion_reasons: list[str] = []
            original_domains = list(domains)

            if domains:
                expanded_domains = await self._expand_domains_for_semantic_types(
                    domains=domains,
                    has_person_reference=has_person_reference,
                    reasoning_trace=reasoning_trace,
                    all_scores=dict.fromkeys(domains, 0.8),
                    expansion_reasons=expansion_reasons,
                    evidence_entities=evidence_entities,
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
                        "person_evidence_sources": person_evidence_sources,
                        "evidence_entities": sorted(evidence_entities),
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
                    # Prevent skill contamination from conversation history:
                    # when intent is confidently classified as conversation, any
                    # skill_name the LLM returned is almost certainly inferred
                    # from prior turns (e.g. a greeting after a skill was used)
                    # rather than from the current query. Clear it so the
                    # response_node does not re-activate the skill ReAct agent.
                    # EXCEPTION (ADR-118): skills declaring `dialogue: true` run
                    # a multi-turn process — the user's conversational reply IS
                    # part of the skill flow, so the detection is preserved.
                    if analysis_result.skill_name and _is_dialogue_skill(
                        analysis_result.skill_name
                    ):
                        logger.info(
                            "chat_override_kept_dialogue_skill",
                            skill_name=analysis_result.skill_name,
                            intent=intent,
                            confidence=confidence,
                            reason="dialogue skill — follow-up turns continue its flow",
                        )
                        reasoning_trace.append(
                            f"Chat Override: dialogue skill kept ({analysis_result.skill_name})"
                        )
                    elif analysis_result.skill_name:
                        logger.info(
                            "chat_override_cleared_skill_name",
                            skill_name=analysis_result.skill_name,
                            intent=intent,
                            confidence=confidence,
                            reason="conversation intent — skill likely inferred from history",
                        )
                        reasoning_trace.append(
                            f"Chat Override: skill_name cleared ({analysis_result.skill_name})"
                        )
                        analysis_result.skill_name = None
                    # Same rationale for semantic_filter_terms: a chat-classified
                    # turn won't reach the planner, but downstream consumers may
                    # still inspect this field; clear it for hygiene.
                    if analysis_result.semantic_filter_terms:
                        analysis_result.semantic_filter_terms = []

            # === STEP 5: Context Resolution (LLM-first) ===
            # Uses context_reference from LLM structured output (Step 2) instead of
            # regex-based reference detection. Eliminates stale routing_history[-1] bug
            # and false positives like "this photo" being treated as a reference.
            context_result, _ = await self.context_resolver.resolve_context(
                query=query,
                state=state,  # type: ignore
                config=config,
                run_id=run_id,
                context_reference=analysis_result.context_reference,
            )
            turn_type = self._determine_turn_type(context_result, immediate_intent)

            # Track context reference detection for debug panel
            intelligent_mechanisms["context_reference_llm"] = {
                "applied": analysis_result.context_reference.has_reference,
                "reference_type": analysis_result.context_reference.reference_type,
                "reference_domain": analysis_result.context_reference.reference_domain,
                "ordinal_positions": analysis_result.context_reference.ordinal_positions,
                "resolved_items_count": len(context_result.items) if context_result else 0,
                "method": context_result.method if context_result else "none",
            }

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
            # Cross-domain coherence: context references can only confirm domains
            # detected by the query analyzer, or fill in when no domain was detected.
            # They can never add or replace with an unrelated domain.
            # Prevents: "the last docker log" after a briefing → context=event overriding devops.
            source_domain = None
            if context_result and context_result.items:
                source_domain = context_result.source_domain
                if source_domain:
                    if not domains:
                        # No domains from analyzer → pure follow-up, context decides
                        domains = [source_domain]
                        reasoning_trace.append(
                            f"REFERENCE (no analyzer domain) → [{source_domain}]"
                        )
                    elif source_domain in domains:
                        # Coherent: context confirms one of the detected domains
                        reasoning_trace.append(f"REFERENCE coherent: {source_domain} in {domains}")
                    else:
                        # Incoherent: analyzer says X, context says Y → keep analyzer
                        logger.info(
                            "context_reference_cross_domain_mismatch",
                            analyzer_domains=domains,
                            context_source_domain=source_domain,
                            action="keeping analyzer domains",
                        )
                        reasoning_trace.append(
                            f"Context reference ignored: analyzer={domains} vs context={source_domain}"
                        )

            # === STEP 9: Semantic Fallback Check ===
            if SemanticFallback.should_fallback(confidence):
                reasoning_trace.append(f"Low confidence ({confidence:.2f}) - Semantic Fallback")

            # === STEP 10: Routing Decision ===
            # Delegated to RoutingDecider (SRP: single service for routing logic)
            # The LLM fills skill_name and domains in one output with no
            # coherence guarantee — resolve the contradiction BEFORE routing
            # AND storage (both read the same resolved name).
            # `user_id` scopes the existence check to the SAME catalogue the
            # prompt advertised (built above from `langgraph_user_id`), so a
            # user's own skill stays reachable and another user's never is.
            _skill_name = effective_skill_name(
                analysis_result.skill_name,
                domains,
                immediate_intent,
                user_id=user_id,
            )
            route_to, final_confidence, bypass = self.routing_decider.decide(
                intent=immediate_intent,
                intent_confidence=confidence,
                domains=domains,
                semantic_score=confidence,
                is_app_help_query=analysis_result.is_app_help_query,
                detected_skill_name=_skill_name,
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

            # Observability: track non-empty semantic_filter_terms emission rate
            # by model. Drives the rollout from 'observe' to 'autocorrect' modes.
            if analysis_result.semantic_filter_terms:
                _term_count = len(analysis_result.semantic_filter_terms)
                _bucket = "1" if _term_count == 1 else "2-3" if _term_count <= 3 else "4+"
                planner_semantic_filter_terms_emitted.labels(
                    model=settings.query_analyzer_llm_model,
                    term_count_bucket=_bucket,
                ).inc()
                logger.info(
                    "semantic_filter_terms_emitted",
                    terms=analysis_result.semantic_filter_terms,
                    term_count=_term_count,
                    model=settings.query_analyzer_llm_model,
                )

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
                # Skill activation (post MCP-domain suppression — see STEP 10)
                detected_skill_name=_skill_name,
                # Indexable vs Semantic — probabilistic hint (frozen tuple)
                semantic_filter_terms=tuple(analysis_result.semantic_filter_terms),
                has_temporal_reference=analysis_result.has_temporal_reference,
            )

        except Exception as e:
            # Best-effort: don't leave the pivot task orphaned if this method
            # failed before the gather awaited it (its own fallback semantics
            # make cancellation safe — no caller consumes its result here).
            if english_query_task is not None and not english_query_task.done():
                english_query_task.cancel()
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
            content = coerce_content_to_text(getattr(msg, "content", ""))
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

        # Specificity rule (see _update_pattern_subsumes_create): a longer UPDATE
        # pattern must win over the shorter CREATE pattern it contains.
        if _update_pattern_subsumes_create(query_lower):
            return "update"

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
        evidence_entities: set[str] | None = None,
    ) -> list[str]:
        """
        Expand domains based on semantic type requirements.

        Example: "trajet chez mon frère" → route requires physical_address +
        person evidence (memory resolver or analyzer LLM) → add contact.

        Two modes (SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED):
        - OFF (default): historical iso-functional person→contact expansion.
        - ON: evidence-driven expansion — every referenced entity (person,
          event, place) whose ontology properties provide a required type
          adds its source domains (capped). For person-only evidence the
          outcome is identical to the iso path (Contact → contact).
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

            if settings.semantic_expansion_evidence_driven_enabled:
                expanded_domains = await expansion_service.expand_domains_evidence_driven(
                    domains=domains,
                    evidence_entities=evidence_entities or set(),
                    required_semantic_types=required_type_names,
                    max_added_domains=settings.semantic_expansion_max_added_domains,
                    query="",
                )
            else:
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
                    provided_types = sorted(
                        sem_type
                        for sem_type in required_type_names
                        if added_domain in expansion_service.get_providers_for_type(sem_type)
                    )
                    if provided_types:
                        reasons.append(
                            f"{added_domain} (provides {', '.join(provided_types)} "
                            "for referenced entity)"
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
