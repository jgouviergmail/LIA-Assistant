"""What the conversation last LOOKED UP of a domain, for a tool that must find where an item lives.

An event lives in a calendar, a task in a list. A planner forgets that container as often as it
gives it, and an item of another container is not found in the default one (ADR-369, lot 5): the
context store's own record of the last lookup answers before any default does.

This is the context LIST (what the last lookup of a domain returned), not what an answer showed:
that other record is ``context/shown_items`` (ADR-367), read on the graph state by a designation.
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.tools.runtime_helpers import ValidatedRuntimeConfig


async def last_lookup_items(config: ValidatedRuntimeConfig, domain: str) -> list[dict[str, Any]]:
    """The items of a domain the context store holds: its last list, then its current item.

    Both are read because the auto-save may route a result to either (``parallel_executor``
    saves a LIST, a direct fetch may only set the current item).

    Args:
        config: Validated runtime config with user_id, session_id, store.
        domain: The context domain (``events``, ``tasks``).

    Returns:
        The items, the last list first; empty when the conversation looked up none.
    """
    manager = ToolContextManager()
    context_list = await manager.get_list(
        user_id=config.user_id,
        session_id=config.session_id,
        domain=domain,
        store=config.store,
    )
    items: list[dict[str, Any]] = list(context_list.items) if context_list else []
    current_item = await manager.get_current_item(
        user_id=config.user_id,
        session_id=config.session_id,
        domain=domain,
        store=config.store,
    )
    if current_item:
        items.append(current_item)
    return items


__all__ = ["last_lookup_items"]
