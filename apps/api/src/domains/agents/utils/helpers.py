"""
Agents domain utilities.
Helper functions for run ID generation and pre-model hooks.

Note: Token counting functions have been moved to utils/token_utils.py
for better organization and to avoid circular dependencies.
"""

import uuid

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def generate_run_id() -> str:
    """
    Generate a unique run ID for tracing a graph execution.

    Returns:
        UUID string for run ID.

    Example:
        >>> run_id = generate_run_id()
        >>> run_id
        '123e4567-e89b-12d3-a456-426614174000'
    """
    return str(uuid.uuid4())


# ============================================================================
# SCORE FORMATTING
# ============================================================================
# Centralized score rounding for consistency across the application.
# All confidence scores, similarity scores, and thresholds should use this.
# ============================================================================

# Default precision for score rounding (2 decimal places)
SCORE_PRECISION: int = 2


def round_score(score: float, precision: int = SCORE_PRECISION) -> float:
    """
    Round a score to the specified precision.

    Centralized function to ensure consistent score formatting across
    the application (logs, storage, API responses).

    Args:
        score: The score to round (0.0 to 1.0 typically).
        precision: Number of decimal places (default: 2).

    Returns:
        Rounded score.

    Examples:
        >>> round_score(0.87654321)
        0.88
        >>> round_score(0.123456, precision=3)
        0.123
    """
    return round(score, precision)


# ============================================================================
# REMOVED UNUSED HELPER FUNCTIONS
# ============================================================================
# The following functions were removed as they are never used and add no value:
#
# - create_pre_model_hook: Never called in production (replaced by LangGraph v1.0 middleware pattern)
#   → Use LangGraph middleware for message history filtering
#
# - format_router_decision_log: Never called in codebase
#   → Use structlog directly: logger.info("router_decision", run_id=..., ...)
#
# - create_system_message: Trivial wrapper around SystemMessage()
#   → Use directly: SystemMessage(content="...")
#
# - create_human_message: Trivial wrapper around HumanMessage()
#   → Use directly: HumanMessage(content="...")
#
# - create_ai_message: Trivial wrapper around AIMessage()
#   → Use directly: AIMessage(content="...")
#
# See CODE_QUALITY.md for best practices on using LangChain message classes.
# ============================================================================
