"""
State cleanup utilities for LangGraph agents.

Provides generic functions for maintaining bounded state sizes by cleaning up
old data from lists and dictionaries in MessagesState.

Prevents unbounded memory growth in long-running conversations.
"""

from typing import Any, TypeVar

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def cleanup_list_by_limit[T](items: list[T], max_items: int, label: str = "items") -> list[T]:
    """
    Keep only the last N items from a list to prevent unbounded growth.

    Generic function that works with any list type (RouterOutput, AgentResult, etc.).
    Preserves most recent items, removes oldest.

    Args:
        items: List of items to clean up.
        max_items: Maximum number of items to keep.
        label: Description of items for logging (e.g., "routing_history", "agent_results").

    Returns:
        Truncated list with at most max_items entries (most recent).

    Example:
        >>> history = [item1, item2, item3, ..., item50]  # 50 items
        >>> cleaned = cleanup_list_by_limit(history, max_items=30, label="routing_history")
        >>> len(cleaned)  # 30 (kept last 30)
        30
    """
    if len(items) <= max_items:
        return items

    kept = items[-max_items:]

    logger.debug(
        "cleanup_list_by_limit",
        label=label,
        original_count=len(items),
        kept_count=len(kept),
        max_items=max_items,
        removed=len(items) - len(kept),
    )

    return kept


def cleanup_dict_by_turn_id(
    results: dict[str, Any], max_results: int, label: str = "results"
) -> dict[str, Any]:
    """
    Cleanup dictionary with turn-based composite keys ("turn_id:agent_name").

    Keeps results from recent N turns (complete turns only).
    Prevents cutting in the middle of a turn execution cycle.

    Strategy:
    - Groups results by turn_id from composite keys
    - Keeps complete turns (all entries for a turn) up to max_results limit
    - Prevents MessagesState from growing unbounded in long sessions

    Args:
        results: Current results dictionary with composite keys (turn_id:agent_name).
        max_results: Maximum number of results to keep (e.g., 30 for ~10 turns x 3 agents).
        label: Description for logging (e.g., "agent_results").

    Returns:
        Cleaned dictionary with at most max_results entries from recent complete turns.

    Example:
        >>> results = {
        ...     "1:contacts_agent": {...},
        ...     "1:emails_agent": {...},
        ...     "2:contacts_agent": {...},
        ...     ...  # 40 results across 15 turns
        ... }
        >>> cleaned = cleanup_dict_by_turn_id(results, max_results=30, label="agent_results")
        >>> len(cleaned)  # 30 (keeping last ~10 complete turns)
        30

    Note:
        This function should be called automatically after each agent execution
        or orchestrator node to maintain memory efficiency.
    """
    if len(results) <= max_results:
        return results

    # Group results by turn_id
    results_by_turn: dict[int, dict[str, Any]] = {}

    for composite_key, result in results.items():
        if ":" in composite_key:
            try:
                turn_id_str, _agent_name = composite_key.split(":", 1)
                turn_id = int(turn_id_str)

                if turn_id not in results_by_turn:
                    results_by_turn[turn_id] = {}
                results_by_turn[turn_id][composite_key] = result
            except ValueError:
                logger.warning(
                    "cleanup_dict_invalid_composite_key",
                    composite_key=composite_key,
                    label=label,
                )
                # Keep malformed keys (backward compatibility)
                if -1 not in results_by_turn:
                    results_by_turn[-1] = {}
                results_by_turn[-1][composite_key] = result
        else:
            # Old format without turn_id - keep in special bucket
            if -1 not in results_by_turn:
                results_by_turn[-1] = {}
            results_by_turn[-1][composite_key] = result

    # Sort turns by ID (most recent last)
    sorted_turns = sorted(results_by_turn.keys())

    # Calculate how many complete turns we can keep
    cleaned = {}
    total_count = 0

    # Start from most recent turns and work backward
    for turn_id in reversed(sorted_turns):
        turn_results = results_by_turn[turn_id]

        # Check if adding this turn would exceed limit
        if total_count + len(turn_results) <= max_results:
            cleaned.update(turn_results)
            total_count += len(turn_results)
        else:
            # Stop adding complete turns (don't cut in middle)
            break

    logger.debug(
        "cleanup_dict_by_turn_id",
        label=label,
        original_count=len(results),
        kept_count=len(cleaned),
        max_results=max_results,
        turns_kept=len({k.split(":")[0] for k in cleaned.keys() if ":" in k}),
        turns_removed=len(sorted_turns)
        - len({k.split(":")[0] for k in cleaned.keys() if ":" in k}),
    )

    return cleaned


def cleanup_dict_by_limit(
    items: dict[str, Any], max_items: int, label: str = "items"
) -> dict[str, Any]:
    """
    Keep only the last N entries from a dictionary.

    Simple dictionary cleanup that preserves insertion order (Python 3.7+).
    Useful for non-turn-based dictionaries.

    Args:
        items: Dictionary to clean up.
        max_items: Maximum number of entries to keep.
        label: Description for logging.

    Returns:
        Truncated dictionary with at most max_items entries (most recent).

    Example:
        >>> cache = {"key1": val1, "key2": val2, ..., "key50": val50}
        >>> cleaned = cleanup_dict_by_limit(cache, max_items=30, label="cache")
        >>> len(cleaned)  # 30
        30

    Note:
        Relies on Python 3.7+ dict insertion order preservation.
    """
    if len(items) <= max_items:
        return items

    # Get last N items (preserving insertion order)
    keys_to_keep = list(items.keys())[-max_items:]
    kept = {k: items[k] for k in keys_to_keep}

    logger.debug(
        "cleanup_dict_by_limit",
        label=label,
        original_count=len(items),
        kept_count=len(kept),
        max_items=max_items,
        removed=len(items) - len(kept),
    )

    return kept


def estimate_dict_memory_size(items: dict[str, Any]) -> int:
    """
    Rough estimation of dictionary memory size in bytes.

    Uses sys.getsizeof for quick approximation (not deep analysis).
    Useful for logging and monitoring state memory usage.

    Args:
        items: Dictionary to estimate.

    Returns:
        Estimated memory size in bytes.

    Example:
        >>> results = {"1:contacts_agent": {...}, "1:emails_agent": {...}}
        >>> size_bytes = estimate_dict_memory_size(results)
        >>> print(f"Memory: {size_bytes / 1024:.2f} KB")
        Memory: 12.5 KB
    """
    import sys

    total_size = sys.getsizeof(items)

    for key, value in items.items():
        total_size += sys.getsizeof(key)
        total_size += sys.getsizeof(value)

    return total_size


__all__ = [
    "cleanup_dict_by_limit",
    "cleanup_dict_by_turn_id",
    "cleanup_list_by_limit",
    "estimate_dict_memory_size",
]
