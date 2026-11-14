"""Which calendar an event lives in, from what the turn already read (ADR-369, lot 5).

Beside the calendar tools, which share it: a planner forgets ``calendar_id`` as often as it
gives it, and an event of another calendar is not found in the primary one.
"""

import structlog

from src.domains.agents.constants import CONTEXT_DOMAIN_EVENTS
from src.domains.agents.tools.last_lookup import last_lookup_items
from src.domains.agents.tools.runtime_helpers import ValidatedRuntimeConfig

logger = structlog.get_logger(__name__)


async def resolve_calendar_id_from_context(
    config: ValidatedRuntimeConfig,
    event_id: str,
) -> str | None:
    """Resolve calendar_id from context store (LIST then DETAILS fallback).

    Searches both LIST and DETAILS store keys for the event, because the
    auto-save classification may route to either key depending on the code path
    (parallel_executor saves to LIST, decorator may save to DETAILS for legacy
    get_* tool names).

    Args:
        config: Validated runtime config with user_id, session_id, store.
        event_id: Event ID to look up.

    Returns:
        calendar_id if found, None otherwise.
    """
    # LIST (last search/list results), then the current item: a direct fetch may
    # set the current item without populating the list.
    context_items = await last_lookup_items(config, CONTEXT_DOMAIN_EVENTS)

    for item in context_items:
        item_id = item.get("id") or item.get("event_id")
        if item_id == event_id:
            calendar_id = item.get("calendar_id")
            logger.info(
                "calendar_id_resolved_from_context",
                event_id=event_id,
                calendar_id=calendar_id,
            )
            return calendar_id

    logger.warning(
        "calendar_id_context_resolution_failed",
        event_id=event_id,
        context_source="none" if not context_items else "not_found",
        fallback="primary",
    )
    return None
