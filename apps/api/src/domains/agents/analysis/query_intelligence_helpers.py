"""
QueryIntelligence Helpers - Centralized utilities for QueryIntelligence access.

Architecture v3 - Intelligence, Autonomy, Relevance.

This module provides utilities for accessing QueryIntelligence from LangGraph state,
handling both object and dict formats transparently.

CONTEXT:
- LangGraph uses msgpack for checkpointing, which doesn't support custom classes
- Router node stores both: dict (for serialization) and object (for methods)
- Other nodes may receive either format depending on execution path
- These helpers provide a unified interface for both cases

Usage:
    from src.domains.agents.analysis.query_intelligence_helpers import (
        get_query_intelligence_from_state,
        get_qi_attr,
    )

    # Get full object (reconstructs from dict if needed)
    qi = get_query_intelligence_from_state(state)

    # Get single attribute (works with both formats)
    domains = get_qi_attr(state, "domains", default=[])
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from src.core.config import settings

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence

T = TypeVar("T")

# State keys
STATE_KEY_QUERY_INTELLIGENCE = "query_intelligence"
STATE_KEY_QUERY_INTELLIGENCE_OBJ = "_query_intelligence_obj"


def get_qi_attr[T](
    state: dict[str, Any],
    attr: str,
    default: T | None = None,
) -> T | None:
    """
    Get an attribute from QueryIntelligence in state (object or dict).

    This is the most efficient way to access a single attribute without
    reconstructing the full object.

    Args:
        state: LangGraph state dict
        attr: Attribute name (e.g., "domains", "english_query")
        default: Default value if attribute not found

    Returns:
        Attribute value or default

    Example:
        domains = get_qi_attr(state, "domains", default=[])
        english_query = get_qi_attr(state, "english_query", default="")
    """
    # Priority 1: Object version (has methods, faster attribute access)
    qi_obj = state.get(STATE_KEY_QUERY_INTELLIGENCE_OBJ)
    if qi_obj is not None:
        return getattr(qi_obj, attr, default)

    # Priority 2: Dict version (serialized)
    qi_dict = state.get(STATE_KEY_QUERY_INTELLIGENCE)
    if qi_dict is not None and isinstance(qi_dict, dict):
        return qi_dict.get(attr, default)  # type: ignore[no-any-return]

    return default


def get_query_intelligence_from_state(
    state: dict[str, Any],
) -> QueryIntelligence | None:
    """
    Get QueryIntelligence object from state, reconstructing if needed.

    Use this when you need the full object with its methods (e.g., to_debug_metrics).
    For simple attribute access, prefer get_qi_attr() which is more efficient.

    Args:
        state: LangGraph state dict

    Returns:
        QueryIntelligence object or None if not available

    Example:
        qi = get_query_intelligence_from_state(state)
        if qi:
            debug_metrics = qi.to_debug_metrics()
    """
    # Priority 1: Object version
    qi_obj = state.get(STATE_KEY_QUERY_INTELLIGENCE_OBJ)
    if qi_obj is not None:
        return qi_obj  # type: ignore[no-any-return]

    # Priority 2: Reconstruct from dict
    qi_dict = state.get(STATE_KEY_QUERY_INTELLIGENCE)
    if qi_dict is not None and isinstance(qi_dict, dict):
        return reconstruct_query_intelligence(qi_dict)

    return None


def reconstruct_query_intelligence(data: dict[str, Any]) -> QueryIntelligence:
    """
    Reconstruct QueryIntelligence object from serialized dict.

    This is needed because LangGraph checkpointing serializes to msgpack,
    which doesn't support custom classes. The router node stores both
    the dict (for checkpointing) and the object (for in-memory access).

    Args:
        data: Dict from QueryIntelligence.to_serializable_dict()

    Returns:
        QueryIntelligence object

    Raises:
        ValueError: If data is None or not a dict
    """
    if data is None or not isinstance(data, dict):
        raise ValueError(f"Cannot reconstruct QueryIntelligence from {type(data)}")

    from src.domains.agents.analysis.query_intelligence import (
        QueryIntelligence,
        UserGoal,
    )

    # Reconstruct UserGoal enum from string
    user_goal_str = data.get("user_goal", "find_info")
    try:
        user_goal = UserGoal(user_goal_str)
    except ValueError:
        user_goal = UserGoal.FIND_INFORMATION

    return QueryIntelligence(
        original_query=data.get("original_query", ""),
        english_query=data.get("english_query", ""),
        english_enriched_query=data.get("english_enriched_query"),
        immediate_intent=data.get("immediate_intent", "search"),
        immediate_confidence=data.get("immediate_confidence", 0.5),
        user_goal=user_goal,
        goal_reasoning=data.get("goal_reasoning", ""),
        implicit_intents=data.get("implicit_intents", []),
        domains=data.get("domains", []),
        primary_domain=data.get("primary_domain", "general"),
        domain_scores=data.get("domain_scores", {}),
        domain_calibrated_scores=data.get("domain_calibrated_scores", {}),
        turn_type=data.get("turn_type", "ACTION"),
        resolved_context=None,  # Complex object, can't reconstruct
        source_turn_id=data.get("source_turn_id"),
        source_domain=data.get("source_domain"),
        resolved_references=data.get("resolved_references"),
        anticipated_needs=data.get("anticipated_needs", []),
        fallback_strategies=data.get("fallback_strategies", []),
        suggested_enrichments=data.get("suggested_enrichments", []),
        route_to=data.get("route_to", "planner"),
        bypass_llm=data.get("bypass_llm", False),
        confidence=data.get("confidence", 0.5),
        user_language=data.get("user_language", settings.default_language),
        reasoning_trace=data.get("reasoning_trace", []),
        intelligent_mechanisms=data.get("intelligent_mechanisms", {}),
        # Validation hints (v3.1) - CRITICAL for semantic validation
        is_mutation_intent=data.get("is_mutation_intent", False),
        has_cardinality_risk=data.get("has_cardinality_risk", False),
        # FOR_EACH pattern detection (v3.1) - CRITICAL for debug panel
        constraint_hints=data.get("constraint_hints", {}),
        for_each_detected=data.get("for_each_detected", False),
        for_each_collection_key=data.get("for_each_collection_key"),
        cardinality_magnitude=data.get("cardinality_magnitude"),
        cardinality_mode=data.get("cardinality_mode", "single"),
        # Knowledge Enrichment (Brave Search) - CRITICAL for debug panel
        encyclopedia_keywords=data.get("encyclopedia_keywords", []),
        is_news_query=data.get("is_news_query", False),
    )


__all__ = [
    "get_qi_attr",
    "get_query_intelligence_from_state",
    "reconstruct_query_intelligence",
    "STATE_KEY_QUERY_INTELLIGENCE",
    "STATE_KEY_QUERY_INTELLIGENCE_OBJ",
]
