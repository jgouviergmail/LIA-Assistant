"""
Utility functions for graph nodes.

This module provides common helper functions used across multiple nodes
to reduce code duplication and ensure consistent behavior.

NOTE: All datetime operations should use src.core.time_utils per the
datetime doctrine. This module re-exports now_in_timezone for convenience.
"""

from langchain_core.runnables import RunnableConfig


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
