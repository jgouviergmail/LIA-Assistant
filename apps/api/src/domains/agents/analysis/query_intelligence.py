"""
QueryIntelligence - Intelligent query analysis dataclass.

Architecture v3 - Intelligence, Autonomy, Relevance.

This module defines the core data structures for intelligent query analysis,
going beyond simple pattern matching to understand the user's true intent.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_LANGUAGE

if TYPE_CHECKING:
    from src.domains.agents.services.reference_resolver import ResolvedContext


class UserGoal(Enum):
    """
    User's ultimate goal (not just the immediate action).

    This represents what the user REALLY wants to accomplish,
    not just the technical operation.
    """

    FIND_INFORMATION = "find_info"  # Looking for specific information
    TAKE_ACTION = "take_action"  # Wants to perform an action
    COMMUNICATE = "communicate"  # Wants to communicate with someone
    PLAN_ORGANIZE = "plan_organize"  # Wants to plan/organize something
    UNDERSTAND = "understand"  # Wants to understand something
    EXPLORE = "explore"  # Exploring without a specific goal


@dataclass(frozen=True)
class QueryIntelligence:
    """
    Intelligent analysis of a user query.

    DIFFERENCE from basic QueryAnalysis:
    - Understands the WHY, not just the WHAT
    - Anticipates future needs
    - Includes explicit reasoning
    - Detects implicit intentions
    - Prepares fallback strategies

    Architecture v3 Principles:
    - Intelligence: Understand user's true intent
    - Autonomy: Prepare for self-healing
    - Pertinence: Know what's relevant
    """

    # === BASIC UNDERSTANDING ===
    original_query: str
    english_query: str  # Semantic Pivot for cross-language matching

    # === INTELLIGENCE: DEEP INTENTION ===

    # Immediate intent (technical action)
    immediate_intent: str  # search | detail | create | update | delete | send | chat | list
    immediate_confidence: float

    # Ultimate goal (what user REALLY wants)
    user_goal: UserGoal
    goal_reasoning: str  # Explanation of the reasoning

    # === FIELDS WITH DEFAULTS (must come after required fields) ===

    # English query with memory refs resolved (e.g., "my wife" → "jean dupond")
    english_enriched_query: str | None = None

    # Implicit intents detected
    implicit_intents: list[str] = field(default_factory=list)
    # Ex: "search contact jean" → implicit: "probably to send something"

    # === PERTINENCE: ENRICHED CONTEXT ===

    # Domains
    domains: list[str] = field(default_factory=list)
    primary_domain: str = "general"
    domain_scores: dict[str, float] = field(default_factory=dict)  # Raw cosine scores
    domain_calibrated_scores: dict[str, float] = field(default_factory=dict)  # Softmax-calibrated

    # Conversational context
    turn_type: str = "ACTION"  # ACTION | REFERENCE_PURE | REFERENCE_ACTION
    resolved_context: "ResolvedContext | None" = None  # ResolvedContext object (not dict)
    source_turn_id: int | None = None
    source_domain: str | None = None

    # Resolved memory references
    resolved_references: dict[str, str] | None = None

    # === AUTONOMY: ANTICIPATION ===

    # Anticipated needs (for proactivity)
    anticipated_needs: list[str] = field(default_factory=list)
    # Ex: If "search dentist appointment" → anticipate: ["may want to cancel", "may want reminder"]

    # Fallback actions if failure
    fallback_strategies: list[str] = field(default_factory=list)
    # Ex: If search_contacts fails → ["broaden search", "search by email"]

    # Suggested enrichments
    suggested_enrichments: list[str] = field(default_factory=list)
    # Ex: For contact → ["recent emails with contact", "last meeting"]

    # === ROUTING ===
    route_to: str = "planner"  # "planner" | "response"
    bypass_llm: bool = False
    confidence: float = 0.0

    # === METADATA ===
    user_language: str = DEFAULT_LANGUAGE
    reasoning_trace: list[str] = field(default_factory=list)  # Reasoning trace

    # === DEBUG: INTELLIGENT MECHANISMS ===
    # Information about intelligent mechanisms for debug panel visibility
    intelligent_mechanisms: dict[str, Any] = field(default_factory=dict)

    # === VALIDATION HINTS (v3.1 - LLM-detected, replaces hardcoded patterns) ===
    # These are detected by QueryAnalyzer LLM and used by semantic_validator
    is_mutation_intent: bool = False  # User wants to create/update/delete/send
    has_cardinality_risk: bool = False  # Query involves "all/every/each/entire"

    # === FOR_EACH PATTERN DETECTION (plan_planner.md Section 14.1) ===
    # Detected by QueryAnalyzer LLM, used by Planner and SemanticValidator
    constraint_hints: dict[str, bool] = field(default_factory=dict)
    # {"has_distance": True, "has_quality": True, "has_iteration": True, ...}

    for_each_detected: bool = False  # User wants action for EACH result
    for_each_collection_key: str | None = None  # "contacts", "events", "places"

    cardinality_magnitude: int | None = None  # None=unknown, 999=all, N=specific
    cardinality_mode: str = "single"  # "single", "multiple", "all", "each"

    # === KNOWLEDGE ENRICHMENT (Brave Search) ===
    # Keywords for encyclopedic knowledge enrichment via Brave Search
    encyclopedia_keywords: list[str] = field(default_factory=list)
    # True if query explicitly asks for news/current events/recent updates
    is_news_query: bool = False

    # === APP SELF-KNOWLEDGE ===
    # True if user asks about the app itself, its features, or usage
    is_app_help_query: bool = False

    # === INTELLIGENT METHODS ===

    def requires_planner(self) -> bool:
        """Check if this query needs the planner."""
        return self.route_to == "planner"

    def is_reference_turn(self) -> bool:
        """Check if this is a reference to previous results."""
        return self.turn_type in ("REFERENCE_PURE", "REFERENCE_ACTION")

    def is_mutation(self) -> bool:
        """Check if this is a mutation (create/update/delete/send)."""
        # v3.1: Use LLM-detected flag (more reliable than intent pattern matching)
        return self.is_mutation_intent or self.immediate_intent in (
            "create",
            "update",
            "delete",
            "send",
        )

    def requires_semantic_validation(self) -> bool:
        """
        Check if plan should trigger semantic validation (LLM-detected risk).

        v3.1: Uses LLM-detected flags instead of hardcoded patterns.
        These are more reliable as the LLM understands context.
        """
        return self.is_mutation_intent or self.has_cardinality_risk

    def get_tool_categories(self) -> list[str]:
        """
        Get tool categories for this query.

        ARCHITECTURE DECISION (v3.1 - Information-rich, Rules-light):
        ============================================================
        Return EMPTY list = no category filtering, only domain filtering.

        RATIONALE:
        - Filtering by intent was causing failures for composite queries
          (e.g., "search for details of contacts named X" needs search + detail)
        - The LLM should see ALL tools for a domain to reason about dependencies
        - Tool dependencies are expressed in manifests (outputs, descriptions)
        - The LLM can intelligently choose the right tool combination

        The intent is still valuable as INFORMATION for the LLM (passed in prompt),
        but should NOT be used to FILTER/RESTRICT the available tools.

        Token cost: ~500-800 tokens/domain instead of ~200
        Benefit: LLM can reason about tool chains (search → detail)
        """
        # Empty = no category filtering, include all tools from detected domains
        # The LLM will use the intent as guidance, not as a filter
        return []

    def should_enrich_results(self) -> bool:
        """
        Decide if results should be enriched.

        Ex: If user_goal=COMMUNICATE and domain=contacts,
        enrich with recent emails exchanged.
        """
        return (
            self.user_goal == UserGoal.COMMUNICATE
            or self.user_goal == UserGoal.UNDERSTAND
            or len(self.suggested_enrichments) > 0
        )

    def get_proactive_suggestions(self) -> list[str]:
        """
        Get proactive suggestions based on analysis.

        Returns suggestions the assistant can offer
        AFTER responding to the initial request.
        """
        suggestions = []

        # If contact search with goal=communicate → suggest sending message
        if self.primary_domain == "contact" and self.user_goal == UserGoal.COMMUNICATE:
            suggestions.append("send_email")
            suggestions.append("send_message")

        # If event search → suggest reminder or modification
        if self.primary_domain == "event":
            suggestions.extend(["set_reminder", "modify_event"])

        # Add anticipated needs
        suggestions.extend(self.anticipated_needs)

        return list(set(suggestions))  # Deduplicate

    def explain_reasoning(self) -> str:
        """
        Explain the analysis reasoning.

        Useful for debugging and showing the user
        that the assistant understood correctly.
        """
        parts = [
            f"Goal: {self.user_goal.value}",
            f"Action: {self.immediate_intent}",
            f"Domain: {self.primary_domain}",
        ]

        if self.implicit_intents:
            parts.append(f"Implicit: {', '.join(self.implicit_intents)}")

        if self.anticipated_needs:
            parts.append(f"Anticipate: {', '.join(self.anticipated_needs)}")

        return " | ".join(parts)

    def to_debug_metrics(self) -> dict[str, Any]:
        """
        Export all scoring metrics for debug panel display.

        Returns a comprehensive dictionary with:
        - Actual measured values (scores, confidences)
        - Configured thresholds for comparison
        - Pass/fail indicators for visual feedback

        Used by StreamingService to emit debug_metrics chunk when DEBUG=true.

        Returns:
            Dictionary organized by pipeline step:
            - intent_detection
            - domain_selection
            - routing_decision
            - tool_selection (placeholder - filled by planner)
            - context_resolution
        """
        from src.core.config.agents import get_debug_thresholds

        thresholds = get_debug_thresholds()
        intent_th = thresholds["intent_detection"]
        domain_th = thresholds["domain_selection"]
        routing_th = thresholds["routing_decision"]
        context_th = thresholds["context_resolution"]

        # Helper to create threshold comparison entry
        def th_check(value: float, threshold: float | int) -> dict[str, Any]:
            return {
                "value": threshold,
                "actual": value,
                "passed": value >= threshold if isinstance(threshold, int | float) else True,
            }

        # Get top calibrated score (used for all decisions)
        top_score = (
            max(self.domain_calibrated_scores.values()) if self.domain_calibrated_scores else 0.0
        )

        return {
            "intent_detection": {
                "detected_intent": self.immediate_intent,
                "confidence": self.immediate_confidence,
                "user_goal": self.user_goal.value,
                "goal_reasoning": self.goal_reasoning,
                "thresholds": {
                    "high_threshold": th_check(
                        self.immediate_confidence, intent_th["high_threshold"]
                    ),
                    "fallback_threshold": th_check(
                        self.immediate_confidence, intent_th["fallback_threshold"]
                    ),
                },
            },
            "domain_selection": {
                "selected_domains": self.domains,
                "primary_domain": self.primary_domain,
                # LLM-based: single confidence score applied to all selected domains
                "top_score": top_score,
                "all_scores": self.domain_calibrated_scores,
                "thresholds": {
                    "primary_min": th_check(top_score, domain_th["primary_min"]),
                    "max_domains": {
                        "value": domain_th["max_domains"],
                        "info": "Maximum domains to select",
                    },
                },
            },
            "routing_decision": {
                "route_to": self.route_to,
                "confidence": self.confidence,
                "bypass_llm": self.bypass_llm,
                "reasoning_trace": self.reasoning_trace,
                "thresholds": {
                    "chat_semantic_threshold": th_check(
                        top_score, routing_th["chat_semantic_threshold"]
                    ),
                    "high_semantic_threshold": th_check(
                        top_score, routing_th["high_semantic_threshold"]
                    ),
                    "min_confidence": th_check(self.confidence, routing_th["min_confidence"]),
                    "chat_override_threshold": {
                        "value": routing_th["chat_override_threshold"],
                        "info": "Chat intent must exceed this to override domain",
                    },
                },
            },
            "context_resolution": {
                "turn_type": self.turn_type,
                "is_reference": self.is_reference_turn(),
                "source_turn_id": self.source_turn_id,
                "source_domain": self.source_domain,
                "resolved_references": self.resolved_references,
                "thresholds": {
                    "confidence_threshold": {
                        "value": context_th["confidence_threshold"],
                        "info": "Minimum confidence for reference resolution",
                    },
                    "active_window_turns": {
                        "value": context_th["active_window_turns"],
                        "info": "Turns considered for active context",
                    },
                },
            },
            "query_info": {
                "original_query": self.original_query,
                "english_query": self.english_query,
                "english_enriched_query": self.english_enriched_query,
                "user_language": self.user_language,
                "implicit_intents": self.implicit_intents,
                "anticipated_needs": self.anticipated_needs,
                "fallback_strategies": self.fallback_strategies,
            },
            "intelligent_mechanisms": self.intelligent_mechanisms,
            # FOR_EACH analysis (v3.1) - bulk operation detection
            "for_each_analysis": {
                "detected": self.for_each_detected,
                "collection_key": self.for_each_collection_key,
                "cardinality_magnitude": self.cardinality_magnitude,
                "cardinality_mode": self.cardinality_mode,
                "constraint_hints": dict(self.constraint_hints) if self.constraint_hints else {},
            },
            # Knowledge Enrichment (Brave Search) - base fields from QueryAnalyzer
            # Full enrichment results are added by _add_debug_metrics_sections() in streaming/service.py
            "knowledge_enrichment": {
                "enabled": True,  # Will be updated by streaming service with actual settings value
                "executed": False,  # Updated by streaming service based on enrichment_result
                "encyclopedia_keywords": list(self.encyclopedia_keywords),
                "is_news_query": self.is_news_query,
            },
        }

    def to_serializable_dict(self) -> dict[str, Any]:
        """
        Convert to a msgpack-serializable dictionary for LangGraph checkpointing.

        Handles:
        - Enum → value string
        - ResolvedContext → dict via to_dict()
        - All other fields → primitive types

        Returns:
            Dictionary with all primitive types (str, int, float, bool, list, dict, None)
        """
        return {
            # Basic understanding
            "original_query": self.original_query,
            "english_query": self.english_query,
            "english_enriched_query": self.english_enriched_query,
            # Intelligence
            "immediate_intent": self.immediate_intent,
            "immediate_confidence": float(self.immediate_confidence),
            "user_goal": self.user_goal.value if self.user_goal else None,  # Enum → str
            "goal_reasoning": self.goal_reasoning,
            "implicit_intents": list(self.implicit_intents),
            # Domains
            "domains": list(self.domains),
            "primary_domain": self.primary_domain,
            # Convert numpy.float64 → float for msgpack serialization
            "domain_scores": {k: float(v) for k, v in self.domain_scores.items()},
            "domain_calibrated_scores": {
                k: float(v) for k, v in self.domain_calibrated_scores.items()
            },
            # Context
            "turn_type": self.turn_type,
            "resolved_context": self.resolved_context.to_dict() if self.resolved_context else None,
            "source_turn_id": self.source_turn_id,
            "source_domain": self.source_domain,
            "resolved_references": (
                dict(self.resolved_references) if self.resolved_references else None
            ),
            # Autonomy
            "anticipated_needs": list(self.anticipated_needs),
            "fallback_strategies": list(self.fallback_strategies),
            "suggested_enrichments": list(self.suggested_enrichments),
            # Routing
            "route_to": self.route_to,
            "bypass_llm": self.bypass_llm,
            "confidence": float(self.confidence),
            # Metadata
            "user_language": self.user_language,
            "reasoning_trace": list(self.reasoning_trace),
            "intelligent_mechanisms": dict(self.intelligent_mechanisms),
            # Validation hints (v3.1) - CRITICAL for semantic validation
            "is_mutation_intent": self.is_mutation_intent,
            "has_cardinality_risk": self.has_cardinality_risk,
            # FOR_EACH pattern detection (plan_planner.md)
            "constraint_hints": dict(self.constraint_hints),
            "for_each_detected": self.for_each_detected,
            "for_each_collection_key": self.for_each_collection_key,
            "cardinality_magnitude": self.cardinality_magnitude,
            "cardinality_mode": self.cardinality_mode,
            # Knowledge Enrichment (Brave Search)
            "encyclopedia_keywords": list(self.encyclopedia_keywords),
            "is_news_query": self.is_news_query,
            # App self-knowledge
            "is_app_help_query": self.is_app_help_query,
        }


@dataclass
class ToolFilter:
    """
    Filter for selecting relevant tools.

    Based on query analysis, not the entire catalogue.
    """

    domains: list[str]
    categories: list[str]
    max_tools: int = 5
    include_context_tools: bool = True
    include_sub_agent_tools: bool = True  # F6: always include delegation tool

    @classmethod
    def from_intelligence(cls, intelligence: QueryIntelligence) -> "ToolFilter":
        """
        Create filter from query intelligence.

        ARCHITECTURE v3.1: Domain-only filtering
        - categories is empty (no intent-based filtering)
        - max_tools increased to accommodate all domain tools
        - LLM sees complete toolset and reasons about dependencies
        """
        return cls(
            domains=intelligence.domains,
            categories=intelligence.get_tool_categories(),  # Returns [] - no filtering
            max_tools=10,  # Increased: include all tools for domain (~6-8 per domain)
            include_context_tools=intelligence.is_reference_turn(),
            include_sub_agent_tools=True,  # F6: always available for planner
        )


@dataclass
class SemanticFallback:
    """
    Semantic fallback configuration.

    When confidence is too low, use core toolkit or ask clarification.
    """

    @staticmethod
    def get_threshold() -> float:
        """Get confidence threshold from settings."""
        try:
            from src.core.config import get_settings

            return get_settings().semantic_fallback_threshold
        except Exception:
            from src.core.constants import SEMANTIC_FALLBACK_THRESHOLD_DEFAULT

            return SEMANTIC_FALLBACK_THRESHOLD_DEFAULT

    @staticmethod
    def should_fallback(confidence: float) -> bool:
        """Check if we should use semantic fallback."""
        return confidence < SemanticFallback.get_threshold()

    @staticmethod
    def get_core_toolkit() -> list[str]:
        """Get core toolkit for fallback."""
        return [
            "perplexity_search",  # Web search
            "wikipedia_search",  # Knowledge base
        ]


@dataclass
class ClarificationRequest:
    """Request for user clarification."""

    question: str
    options: list[str] = field(default_factory=list)
    context: str = ""
    confidence: float = 0.0
