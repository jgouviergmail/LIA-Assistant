"""Response-owned, optional previews; cancellation joins every native child call."""

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID

import structlog
from langgraph.config import get_stream_writer
from pydantic import ValidationError

from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.display.jev_qualification import (
    compatible_collection_item,
    qualify_collection,
)

logger = structlog.get_logger(__name__)


async def _publish_collection(
    writer: Callable[[dict[str, Any]], None],
    user_id: UUID,
    run_id: str,
    query: str,
    items: list[RegistryItem],
) -> None:
    try:
        result = await qualify_collection(user_id=user_id, run_id=run_id, query=query, items=items)
        if result is not None:
            writer(
                {
                    "type": "result_preview",
                    "metadata": {"collection": result.model_dump(mode="json")},
                }
            )
    except Exception as exc:
        # Source text, prompts, credentials and provider bodies never enter logs.
        logger.warning("jev_preview_unavailable", run_id=run_id, error_type=type(exc).__name__)


async def _publish(
    writer: Callable[[dict[str, Any]], None],
    user_id: UUID,
    run_id: str,
    query: str,
    registry: dict[str, Any],
) -> None:
    groups: dict[RegistryItemType, list[RegistryItem]] = {}
    for value in registry.values():
        try:
            item = RegistryItem.model_validate(value)
        except ValidationError:
            logger.warning("jev_preview_invalid_item", run_id=run_id)
            continue
        if compatible_collection_item(item):
            groups.setdefault(item.type, []).append(item)
    async with asyncio.TaskGroup() as group:
        for items in groups.values():
            group.create_task(_publish_collection(writer, user_id, run_id, query, items))


class CollectionPreview:
    """One ephemeral response job, never checkpointed or detached from accounting."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None

    def start(self, state: dict[str, Any], registry: dict[str, Any] | None, run_id: str) -> None:
        context = runtime_context_if_running()
        if (
            context is None
            or context.is_automated_source
            or context.voice_enabled
            or context.browser_context is None
        ):
            return
        if get_qi_attr(state, "immediate_intent", "") != "search" or get_qi_attr(
            state, "is_mutation_intent", False
        ):
            return
        query = get_qi_attr(state, "english_enriched_query", "") or get_qi_attr(
            state, "english_query", ""
        )
        if (
            not isinstance(query, str)
            or not query.strip()
            or not registry
            or self._task is not None
        ):
            return
        try:
            writer = get_stream_writer()
        except RuntimeError:
            # A non-streaming graph invocation still produces its ordinary answer.
            return
        self._task = asyncio.create_task(_publish(writer, context.user_id, run_id, query, registry))

    async def close(self) -> None:
        """Stop unfinished optional work before the response's tracker closes."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
