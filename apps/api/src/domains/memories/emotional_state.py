"""
Emotional state computation from memory search results.

Migrated from infrastructure/store/semantic_store.py to operate on
Memory ORM objects instead of LangGraph store Items.

Algorithm:
1. If ANY memory has emotional_weight <= -5 -> DANGER (sensitive zone)
2. If MAJORITY of memories have emotional_weight >= 3 -> COMFORT (positive zone)
3. Otherwise -> NEUTRAL (factual mode)

Used by:
- build_psychological_profile() in memory_injection.py
  -> Drives DANGER_DIRECTIVE vs NORMAL_DIRECTIVE selection
  -> Visual feedback in UI (colored indicator)

Phase: v1.14.0 — Memory migration to PostgreSQL custom
Created: 2026-03-30
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.memories.models import Memory


class EmotionalState(str, Enum):
    """Aggregate emotional state computed from memory search results.

    Used for visual feedback in the UI and context-aware responses.
    """

    COMFORT = "comfort"  # Positive memories dominant (green indicator)
    DANGER = "danger"  # Negative/sensitive memories present (red indicator)
    NEUTRAL = "neutral"  # Factual mode, no strong emotions (gray indicator)


def compute_emotional_state(
    memories: list[Memory] | list[tuple[Memory, float]],
) -> EmotionalState:
    """Compute aggregate emotional state from memory search results.

    Accepts either plain Memory objects or (Memory, score) tuples
    from search_by_relevance results.

    Algorithm:
        1. If ANY memory has emotional_weight <= -5 -> DANGER (sensitive zone)
        2. If MAJORITY of memories have emotional_weight >= 3 -> COMFORT
        3. Otherwise -> NEUTRAL (factual mode)

    Args:
        memories: List of Memory objects or (Memory, score) tuples.

    Returns:
        EmotionalState enum value.
    """
    if not memories:
        return EmotionalState.NEUTRAL

    emotional_weights: list[int | float] = []

    for item in memories:
        # Support both Memory objects and (Memory, score) tuples
        memory = item[0] if isinstance(item, tuple) else item
        weight = getattr(memory, "emotional_weight", 0)
        if isinstance(weight, int | float):
            emotional_weights.append(weight)

    if not emotional_weights:
        return EmotionalState.NEUTRAL

    # Check for danger zones (any strongly negative memory)
    if any(w <= -5 for w in emotional_weights):
        return EmotionalState.DANGER

    # Check for comfort zone (majority positive)
    positive_count = sum(1 for w in emotional_weights if w >= 3)
    if positive_count > len(emotional_weights) / 2:
        return EmotionalState.COMFORT

    return EmotionalState.NEUTRAL
