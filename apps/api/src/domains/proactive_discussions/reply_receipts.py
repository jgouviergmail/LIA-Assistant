"""A native extraction receipt clears only its own transient reply restriction.

Memory extraction calls these after it handled a turn; they never raise, because
a receipt that fails leaves the guard in place (ADR-359), which is the safe side.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import structlog

from src.domains.proactive_discussions.replies import acknowledge_reply
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def acknowledge_extracted_reply(owner: str | None, run_id: str | None) -> None:
    """Clear the guard of the reply the extraction of ``run_id`` processed.

    Args:
        owner: The account, as the extraction carries it.
        run_id: The turn whose reply was processed.
    """
    if not owner or not run_id:
        return
    try:
        async with get_db_context() as db:
            await acknowledge_reply(db, UUID(owner), run_id, now=datetime.now(UTC))
    except Exception as exc:
        logger.warning("discussion_reply_receipt_failed", error_type=type(exc).__name__)


async def acknowledge_empty_reply(owner: str | None, run_id: str | None, result: str) -> None:
    """A reply the extractor found nothing to learn from is processed all the same."""
    if result.strip() == "[]":
        await acknowledge_extracted_reply(owner, run_id)


async def acknowledge_completed_reply(
    owner: str | None,
    run_id: str | None,
    parsed_count: int,
    entries: Sequence[Mapping[str, object]],
) -> None:
    """Acknowledge only when every parsed action was stored: a partial store keeps the guard."""
    if len(entries) == parsed_count and all(row.get("stored") is not False for row in entries):
        await acknowledge_extracted_reply(owner, run_id)
