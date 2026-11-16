"""Memory resolution in tests: the production phase object, never a hand-made shape.

Latency lot 1 split the memory phase in two: ``MemoryResolver.begin`` starts the
broad retrieval and the reference chain, the analyzer awaits the facts, joins
the rest after its own call and closes the phase on every exit. These helpers
keep that contract in the tests: the double hands back a REAL
``PendingMemoryResolution`` over finished tasks, and the direct helper joins and
closes exactly as the analyzer does.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from langchain_core.runnables import RunnableConfig

from src.domains.agents.services.analysis.memory_resolver import (
    MemoryResolution,
    MemoryResolver,
    PendingMemoryResolution,
)
from src.domains.agents.services.memory_reference_resolution_service import (
    ResolvedReferences,
)


def resolver_answering(
    resolution: MemoryResolution, *, facts_error: Exception | None = None
) -> MagicMock:
    """A resolver whose ``begin`` hands back a phase already answering ``resolution``.

    Args:
        resolution: What the phase answers once joined.
        facts_error: Raised by the broad retrieval instead of answering.

    Returns:
        A double whose ``begin`` records its arguments (query, user id, config).
    """

    async def facts() -> list[str] | None:
        if facts_error is not None:
            raise facts_error
        return resolution.facts

    async def chain() -> tuple[list[str], ResolvedReferences | None]:
        return resolution.references, resolution.resolved

    def begin(_query: str, _user_id: str, _config: RunnableConfig) -> PendingMemoryResolution:
        return PendingMemoryResolution(
            asyncio.ensure_future(facts()), asyncio.ensure_future(chain())
        )

    resolver = MagicMock()
    resolver.begin = MagicMock(side_effect=begin)
    return resolver


async def resolve_all(
    resolver: MemoryResolver, query: str, user_id: str, config: RunnableConfig
) -> MemoryResolution:
    """Run both tracks and join them, closing the phase as the analyzer does.

    Args:
        resolver: The resolver under test.
        query: User's original query.
        user_id: User ID for memory retrieval.
        config: RunnableConfig for callback propagation.

    Returns:
        The joined resolution.
    """
    pending = resolver.begin(query, user_id, config)
    try:
        return await pending.resolution()
    finally:
        await pending.close()
