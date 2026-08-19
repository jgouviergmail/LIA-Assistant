"""The single construction site of the run-scoped context (ADR-231).

Lives outside ``services/orchestration/service.py`` for two reasons. That module
is frozen by the file-size ratchet at 713 logical SLOC and may only shrink, so a
seventeen-field constructor cannot live there. And keeping the mapping in one
named place makes it reviewable as a whole: it is the exact counterpart of the
``RunnableConfig(configurable={...})`` literal it will eventually replace, so the
two can be diffed against each other while both planes coexist.

The parameter names deliberately mirror the caller's local variables (``user_``
prefixes included) rather than the context's field names: this is an adapter
between the streaming service's vocabulary and the context's, and hiding that
seam would only make the call site harder to check against the bag above it.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from langgraph.store.base import BaseStore

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.models import MessagesState

__all__ = ["build_runtime_context"]


def build_runtime_context(
    *,
    state: MessagesState,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    memory_store: BaseStore | None = None,
    tool_deps: Any = None,
    browser_context: Any = None,
    user_message: str = "",
    side_channel_queue: asyncio.Queue | None = None,
    user_memory_enabled: bool = False,
    user_journals_enabled: bool = False,
    user_psyche_enabled: bool = False,
    user_display_mode: str | None = None,
    user_execution_mode: str | None = None,
    is_automated_source: bool = False,
) -> LiaRuntimeContext:
    """Build the context of one conversation run.

    Every argument comes from the same value the chokepoint puts in
    ``configurable``, so the two planes cannot disagree while they coexist.
    ``None`` is treated as "not supplied" for the string preferences, letting the
    context's own defaults (settings-driven, never inline literals) apply.

    Args:
        state: Graph state; the display name, timezone and language are read
            from it directly rather than re-passed, so the call site cannot
            forward a value that disagrees with the state it came from.
        user_id: The acting user. Stays a ``uuid.UUID`` — no string twin.
        conversation_id: The conversation; also becomes the LangGraph thread.
        memory_store: Long-term memory store compiled into the graph.
        tool_deps: Tool dependency container (live object, by reference).
        browser_context: Consented geolocation and client hints, when supplied.
        user_message: Raw user message, for location-phrase detection.
        side_channel_queue: SSE side channel (live object, by reference).
        user_memory_enabled: User preference — long-term memory.
        user_journals_enabled: User preference — personal journals.
        user_psyche_enabled: User preference — psyche engine.
        user_display_mode: Render mode; ``None`` keeps the context default.
        user_execution_mode: Pipeline or ReAct; ``None`` keeps the default.
        is_automated_source: True for runs the user did not type.

    Returns:
        A ready-to-inject :class:`LiaRuntimeContext`.
    """
    optional: dict[str, Any] = {
        "display_mode": user_display_mode,
        "execution_mode": user_execution_mode,
        "timezone": state.get("user_timezone"),
        "language": state.get("user_language"),
    }

    return LiaRuntimeContext.for_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        store=memory_store,
        memory_enabled=user_memory_enabled,
        journals_enabled=user_journals_enabled,
        psyche_enabled=user_psyche_enabled,
        is_automated_source=is_automated_source,
        display_name=state.get("user_display_name"),
        deps=tool_deps,
        browser_context=browser_context,
        user_message=user_message,
        side_channel_queue=side_channel_queue,
        **{key: value for key, value in optional.items() if value is not None},
    )
