"""
Utility functions for graph nodes.

This module provides common helper functions used across multiple nodes
to reduce code duplication and ensure consistent behavior.

NOTE: All datetime operations should use src.core.time_utils per the
datetime doctrine. This module re-exports now_in_timezone for convenience.
"""

from datetime import datetime, timedelta

from langchain_core.runnables import RunnableConfig

from src.core.time_utils import now_in_timezone


def get_datetime_in_timezone(user_timezone: str = "Europe/Paris") -> datetime:
    """
    Get current datetime in the user's timezone.

    Delegates to time_utils.now_in_timezone() per datetime doctrine.
    Falls back to DEFAULT_USER_DISPLAY_TIMEZONE if timezone is invalid.

    Args:
        user_timezone: User's IANA timezone (e.g., "Europe/Paris")

    Returns:
        datetime: Current datetime in the user's timezone (always aware)
    """
    return now_in_timezone(user_timezone)


def get_temporal_context(user_timezone: str = "Europe/Paris") -> dict[str, str]:
    """
    Generate temporal context for resolution and prompts.

    Provides formatted date strings for today, tomorrow, next week, etc.
    Used by context_loader_node for temporal resolution.

    Args:
        user_timezone: User's IANA timezone (e.g., "Europe/Paris")

    Returns:
        Dict with temporal reference values:
        - current_datetime: "2024-12-22 15:30"
        - today_date: "22 December 2024"
        - tomorrow_date: "23 December 2024"
        - next_week_start: "29 December 2024"
        - next_week_end: "04 January 2025"
        - date_plus_3: "25 December 2024"
    """
    now = get_datetime_in_timezone(user_timezone)
    tomorrow = now + timedelta(days=1)
    next_week_start = now + timedelta(days=(7 - now.weekday()))
    next_week_end = next_week_start + timedelta(days=6)

    return {
        "current_datetime": now.strftime("%Y-%m-%d %H:%M"),
        "today_date": now.strftime("%d %B %Y"),
        "tomorrow_date": tomorrow.strftime("%d %B %Y"),
        "next_week_start": next_week_start.strftime("%d %B %Y"),
        "next_week_end": next_week_end.strftime("%d %B %Y"),
        "date_plus_3": (now + timedelta(days=3)).strftime("%d %B %Y"),
    }


def extract_session_id_from_config(config: RunnableConfig, required: bool = True) -> str:
    """
    Extract session_id from LangGraph config.thread_id (source of truth).

    In LangGraph v1.0, the thread_id in config.configurable is the canonical source
    for session/conversation identification. This is especially critical after HITL
    resumption, where state is loaded from checkpoint but session_id is NOT persisted
    in the state itself.

    Args:
        config: RunnableConfig with configurable.thread_id containing the session/conversation ID
        required: If True, raises ValueError when thread_id is missing.
                 If False, returns empty string when missing.

    Returns:
        str: The session_id extracted from thread_id

    Raises:
        ValueError: If required=True and thread_id is missing from config.configurable

    Examples:
        >>> config = {"configurable": {"thread_id": "conv_123"}}
        >>> extract_session_id_from_config(config)
        'conv_123'

        >>> config = {"configurable": {}}
        >>> extract_session_id_from_config(config, required=False)
        ''

        >>> extract_session_id_from_config(config, required=True)
        ValueError: thread_id missing in config.configurable...

    Note:
        This function uses config.get() to safely access nested dictionaries,
        defaulting to empty dict if "configurable" key doesn't exist.
    """
    session_id = config.get("configurable", {}).get("thread_id", "")

    if required and not session_id:
        raise ValueError(
            "thread_id missing in config.configurable. "
            "This is required for session-based operations. "
            "Ensure RunnableConfig has configurable={'thread_id': conversation_id}"
        )

    return session_id
