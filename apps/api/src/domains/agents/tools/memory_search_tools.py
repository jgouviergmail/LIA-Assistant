"""Memory search tool — long-term memory as an active lookup (ADR-313).

The profile injected each turn is ranked on the person's MESSAGE: it holds what
their words evoke, and nothing about a subject the turn discovers on the way —
the sender of an e-mail the loop just read, a place named in a document, « the
rules I gave you ». This tool lets the ReAct loop and the planner look such a
subject up through the one lookup door (``memories.search``), under the same
preference and the same relevance floor as the injection.

Read-only, no HITL, no OAuth — the memories belong to the person. Nothing here
is prose for the person: the messages are technical English the model reworded
(ADR-256), and a failure never reads as « nothing is remembered » (ADR-303).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.domains.agents.constants import AGENT_MEMORY
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.memory.catalogue_manifests import (
    MEMORY_SEARCH_CATEGORIES,
    MEMORY_SEARCH_QUERY_MIN_CHARS,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.lookup_parameters import bounded_count
from src.domains.agents.tools.memory_tools import MemoryCategoryType
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.memories.models import Memory

logger = structlog.get_logger(__name__)

#: Emotional weight at or below which a memory is handled as painful — the
#: injection's own threshold for turning a nuance into an obligation.
_PAINFUL_WEIGHT = -3


def _memory_item(memory: Memory, score: float) -> dict[str, Any]:
    """One memory as the model reads it."""
    recorded = getattr(memory, "created_at", None)
    return {
        "content": memory.content,
        "category": memory.category,
        "usage_nuance": memory.usage_nuance or None,
        "sensitive": memory.category == "sensitivity"
        or (memory.emotional_weight or 0) <= _PAINFUL_WEIGHT,
        "recorded_on": recorded.date().isoformat() if recorded else None,
        "relevance": round(score, 2),
    }


def _refusal(message: str, code: ToolErrorCode) -> UnifiedToolOutput:
    return UnifiedToolOutput.failure(message=message, error_code=code.value)


@read_tool(name="search_memories", agent_name=AGENT_MEMORY)
async def search_memories_tool(
    query: Annotated[
        str,
        "The subject to look up, in a few words, in the user's language "
        "(memories are stored as they were said).",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    category: Annotated[
        MemoryCategoryType | None,
        "Narrow to one family (procedural = standing instructions); omit for all.",
    ] = None,
    max_results: Annotated[int | None, "Most memories to return (default: the maximum)."] = None,
) -> UnifiedToolOutput:
    """Look up what LIA remembers about the user on a given subject.

    Args:
        query: The subject to look up.
        runtime: LangChain tool runtime (injected).
        category: One memory family to narrow to, or None for all.
        max_results: Result ceiling, clamped to ``settings.memory_max_results``.

    Returns:
        UnifiedToolOutput with ``{memories: [...], count}``, most relevant first;
        a typed failure when the search is switched off or could not run.
    """
    config = validate_runtime_config(runtime, "search_memories_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    context = tool_runtime_context(runtime)
    if context is not None and not context.memory_enabled:
        return _refusal(
            "Long-term memory is switched off in the user's settings: nothing was "
            "searched. Do not claim that nothing is remembered.",
            ToolErrorCode.FORBIDDEN,
        )
    needle = query.strip()
    if len(needle) < MEMORY_SEARCH_QUERY_MIN_CHARS:
        return _refusal(
            f"Give a subject to look up (at least {MEMORY_SEARCH_QUERY_MIN_CHARS} characters).",
            ToolErrorCode.INVALID_INPUT,
        )
    if category is not None and category not in MEMORY_SEARCH_CATEGORIES:
        return _refusal(
            f"Unknown category; accepted: {', '.join(MEMORY_SEARCH_CATEGORIES)}.",
            ToolErrorCode.INVALID_PARAM_VALUE,
        )

    from src.domains.agents.middleware.memory_injection import track_memory_usage
    from src.domains.memories.search import search_memories

    limit = bounded_count(max_results, settings.memory_max_results)
    user_id = UUID(str(config.user_id))
    results = await search_memories(
        user_id,
        needle,
        limit=limit,
        min_score=settings.memory_min_search_score,
        categories={category} if category else None,
    )
    if results is None:
        return _refusal(
            "The memory search could not run right now (no embedding). Say it could "
            "not be checked; never conclude that nothing is remembered.",
            ToolErrorCode.DEPENDENCY_ERROR,
        )
    if results:
        await track_memory_usage(str(user_id), results)

    memories = [_memory_item(memory, score) for memory, score in results]
    # Counts only: the subject and the memories are the person's words.
    logger.info(
        "memory_search_tool_completed",
        user_id=str(user_id),
        found=len(memories),
        limit=limit,
        category=category,
    )
    return UnifiedToolOutput.data_success(
        message=(
            f"{len(memories)} memory(ies) match this lookup."
            if memories
            else "No memory matches this lookup."
        ),
        structured_data={"memories": memories, "count": len(memories)},
    )


__all__ = ["search_memories_tool"]
