"""
Routing Decider - Decides routing based on intent, domains, and semantic scores.

This service encapsulates routing decision logic extracted from QueryAnalyzerService.
It determines whether to route to "response" (chat) or "planner" (action execution).

Design Philosophy:
- SRP: Single responsibility for routing decisions
- Clear logic: Explicit rules for routing
- Composition: Used by QueryAnalyzerService as a component
"""

import structlog

logger = structlog.get_logger(__name__)


class RoutingDecider:
    """
    Decides routing destination based on query analysis results.

    Routing rules:
    1. Chat intent without domains → response (conversational)
    2. Data intents with domains → planner (action execution)
    3. High semantic score → planner (likely data operation)
    4. No domains → response (fallback to chat)
    """

    def __init__(
        self,
        chat_semantic_threshold: float = 0.4,
        high_semantic_threshold: float = 0.7,
        min_confidence: float = 0.3,
    ):
        """
        Initialize RoutingDecider with threshold configuration.

        Args:
            chat_semantic_threshold: Threshold for chat mode routing
            high_semantic_threshold: Threshold for bypassing LLM with high confidence
            min_confidence: Minimum confidence for planner routing
        """
        self.chat_semantic_threshold = chat_semantic_threshold
        self.high_semantic_threshold = high_semantic_threshold
        self.min_confidence = min_confidence

    def decide(
        self,
        intent: str,
        intent_confidence: float,
        domains: list[str],
        semantic_score: float,
    ) -> tuple[str, float, bool]:
        """
        Decide routing based on intent, domains, and semantic scores.

        Returns:
            Tuple of (route_to, confidence, bypass_llm) where:
            - route_to: "response" or "planner"
            - confidence: Routing confidence score
            - bypass_llm: Whether to bypass LLM in planner (high confidence)
        """
        # Rule 1: Chat intent without domains → response
        if intent == "chat" and (not domains or semantic_score < self.chat_semantic_threshold):
            return "response", intent_confidence, False

        # Rule 2: Data intents with domains → planner
        DATA_INTENTS = {"search", "list", "send", "create", "update", "delete", "detail"}
        if intent in DATA_INTENTS and domains:
            return "planner", max(intent_confidence, self.min_confidence), True

        # Rule 3: High semantic score → planner
        if domains and semantic_score >= self.high_semantic_threshold:
            return "planner", semantic_score, True

        # Rule 4: No domains → fallback to chat mode
        if not domains:
            logger.info(
                "routing_fallback_no_domains",
                intent=intent,
                semantic_score=round(semantic_score, 3),
                reason="No domains selected, falling back to response",
            )
            return "response", semantic_score, False

        # Default → planner with lower confidence
        return "planner", semantic_score, False


# =============================================================================
# SINGLETON
# =============================================================================

_decider: RoutingDecider | None = None


def get_routing_decider(
    chat_semantic_threshold: float | None = None,
    high_semantic_threshold: float | None = None,
    min_confidence: float | None = None,
) -> RoutingDecider:
    """
    Get singleton RoutingDecider instance.

    Args:
        chat_semantic_threshold: Override default chat threshold
        high_semantic_threshold: Override default high threshold
        min_confidence: Override default min confidence

    Note: Thresholds are only used on first initialization.
          Use reset_routing_decider() to reconfigure.
    """
    global _decider
    if _decider is None:
        kwargs = {}
        if chat_semantic_threshold is not None:
            kwargs["chat_semantic_threshold"] = chat_semantic_threshold
        if high_semantic_threshold is not None:
            kwargs["high_semantic_threshold"] = high_semantic_threshold
        if min_confidence is not None:
            kwargs["min_confidence"] = min_confidence

        _decider = RoutingDecider(**kwargs)
    return _decider


def reset_routing_decider() -> None:
    """Reset singleton (for testing or reconfiguration)."""
    global _decider
    _decider = None


__all__ = [
    "RoutingDecider",
    "get_routing_decider",
    "reset_routing_decider",
]
