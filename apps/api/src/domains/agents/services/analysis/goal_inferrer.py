"""
Goal Inferrer - Infers user goal from query, intent, and context.

This service encapsulates goal inference logic extracted from QueryAnalyzerService.
It uses pattern matching and conversation context to infer the user's ultimate goal.

Design Philosophy:
- SRP: Single responsibility for goal inference
- Pattern-based: Fast pattern matching for common scenarios
- Context-aware: Uses conversation history for better inference
- Composition: Used by QueryAnalyzerService as a component
"""

from langchain_core.messages import BaseMessage

from src.domains.agents.analysis.query_intelligence import UserGoal

# =============================================================================
# GOAL PATTERNS (Module-level constants for performance)
# =============================================================================

_GOAL_PATTERNS: dict[tuple[str, str], tuple[UserGoal, str]] = {
    ("search", "contacts"): (UserGoal.COMMUNICATE, "Contact search = probably to communicate"),
    ("send", "emails"): (UserGoal.COMMUNICATE, "Send email = communication"),
    ("search", "events"): (UserGoal.PLAN_ORGANIZE, "Event search = planning"),
    ("create", "events"): (UserGoal.PLAN_ORGANIZE, "Create event = planning"),
    ("search", "drive"): (UserGoal.FIND_INFORMATION, "File search = need information"),
    ("search", "perplexity"): (UserGoal.UNDERSTAND, "Web search = need to understand"),
    ("search", "wikipedia"): (UserGoal.UNDERSTAND, "Wikipedia search = need to understand"),
    ("search", "tasks"): (UserGoal.PLAN_ORGANIZE, "Task search = organization"),
    ("create", "tasks"): (UserGoal.TAKE_ACTION, "Create task = action"),
}

_DEFAULT_GOALS: dict[str, tuple[UserGoal, str]] = {
    "search": (UserGoal.FIND_INFORMATION, "Information search"),
    "detail": (UserGoal.FIND_INFORMATION, "Need details"),
    "create": (UserGoal.TAKE_ACTION, "Creation requested"),
    "update": (UserGoal.TAKE_ACTION, "Modification requested"),
    "delete": (UserGoal.TAKE_ACTION, "Deletion requested"),
    "send": (UserGoal.COMMUNICATE, "Communication with someone"),
    "list": (UserGoal.EXPLORE, "Exploration/listing"),
    "chat": (UserGoal.UNDERSTAND, "General conversation"),
}


class GoalInferrer:
    """
    Infers the user's ultimate goal using pattern matching.

    Uses fast pattern matching against common intent+domain combinations,
    and falls back to conversation context analysis for ambiguous cases.
    """

    def infer(
        self,
        query: str,
        intent: str,
        domains: list[str],
        messages: list[BaseMessage],
    ) -> tuple[UserGoal, str]:
        """
        Infer the user's ultimate goal.

        Strategy:
        1. Fast pattern matching for common intent+domain combinations
        2. Conversation context analysis for ambiguous cases
        3. Default based on intent type

        Args:
            query: User's query
            intent: Detected intent (search, create, update, delete, send, chat, etc.)
            domains: Detected domains (contacts, emails, events, etc.)
            messages: Conversation history for context

        Returns:
            Tuple of (goal, reasoning) where:
            - goal: UserGoal enum value
            - reasoning: Human-readable explanation
        """
        # Strategy 1: Fast pattern matching
        for pattern, (goal, reasoning) in _GOAL_PATTERNS.items():
            pattern_intent, pattern_domain = pattern
            if intent == pattern_intent and pattern_domain in domains:
                return goal, reasoning

        # Strategy 2: Infer from conversation context
        if len(messages) > 2:
            context_goal = self._infer_from_conversation_context(messages, intent)
            if context_goal:
                return context_goal

        # Strategy 3: Default based on intent
        return _DEFAULT_GOALS.get(intent, (UserGoal.FIND_INFORMATION, "Default"))

    def _infer_from_conversation_context(
        self,
        messages: list[BaseMessage],
        intent: str,
    ) -> tuple[UserGoal, str] | None:
        """
        Infer goal from recent conversation context.

        Analyzes the last 4 messages to detect patterns like:
        - Contact search followed by send → COMMUNICATE
        - Email search followed by search → UNDERSTAND

        Args:
            messages: Conversation history
            intent: Current intent

        Returns:
            Tuple of (goal, reasoning) or None if no pattern detected
        """
        recent = messages[-4:]
        for msg in recent:
            content = str(msg.content).lower() if hasattr(msg, "content") else ""
            if "contact" in content and intent == "send":
                return UserGoal.COMMUNICATE, "Following contact search"
            if "email" in content and intent == "search":
                return UserGoal.UNDERSTAND, "Following email search"

        return None


# =============================================================================
# SINGLETON
# =============================================================================

_inferrer: GoalInferrer | None = None


def get_goal_inferrer() -> GoalInferrer:
    """Get singleton GoalInferrer instance."""
    global _inferrer
    if _inferrer is None:
        _inferrer = GoalInferrer()
    return _inferrer


def reset_goal_inferrer() -> None:
    """Reset singleton (for testing)."""
    global _inferrer
    _inferrer = None


__all__ = [
    "GoalInferrer",
    "get_goal_inferrer",
    "reset_goal_inferrer",
]
