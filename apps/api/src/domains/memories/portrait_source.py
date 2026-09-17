"""The long-term memories, as the user portrait reads them (2026-09-16, part B).

Installed into ``domains/shared/portrait_sources`` so ``journals`` reads it
without importing this domain. Three gates, read AT CALL TIME: the deployment
ceiling, the operator switch (``is_capability_enabled``) and the person's own
preference. One bounded page, most important first, beside the EXACT total;
each item carries the emotional label the memory injection already uses and
the ISO date the memory was recorded. A read that fails is ``unavailable`` —
a blind source is named, never read as empty.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.memories.emotional_state import emotional_label
from src.domains.memories.repository import MemoryRepository
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    SourceBudget,
    clamp_item,
    empty_section,
    install_portrait_source,
    portrait_lines,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "memories"


async def _allowed(user_id: UUID) -> bool:
    if not settings.memory_extraction_enabled:
        return False
    if not await is_capability_enabled(PlatformCapability.MEMORY):
        return False
    async with get_db_context() as db:
        user = await db.get(User, user_id)
    return bool(user is not None and user.memory_enabled)


async def read_memories(
    *, user_id: UUID, language: str, budget: SourceBudget
) -> PortraitSourceSection:
    """Render the person's memories for the consolidation prompt.

    Args:
        user_id: The account.
        language: Unused — a memory is written in the person's own words.
        budget: How many items, how long each.

    Returns:
        The section; never raises.
    """
    try:
        if not await _allowed(user_id):
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            repo = MemoryRepository(db)
            total = await repo.get_count_for_user(user_id)
            rows = (
                await repo.list_for_portrait(user_id, limit=budget.max_items)
                if total and budget.max_items > 0
                else []
            )
        if not rows:
            return empty_section(KEY, "empty", total=total)
        lines = portrait_lines()
        items = [
            lines["memories_item"].format(
                category=row.category or "personal",
                label=emotional_label(int(row.emotional_weight or 0)),
                content=clamp_item(row.content or "", budget.item_max_chars),
                recorded=f"{row.created_at:%Y-%m-%d}" if row.created_at else "",
            )
            for row in rows
        ]
        header = lines["memories_header"].format(shown=len(items), total=total)
        return PortraitSourceSection(
            key=KEY, status="used", text="\n".join([header, *items]), used=len(items), total=total
        )
    except Exception as exc:  # noqa: BLE001 — a blind source is named, never read as empty
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")


#: Where this source's freshness is read (the consolidation's eligibility).
FRESHNESS = FreshnessProbe(table="memories", user_column="user_id", stamp_column="updated_at")

# Installed at import for every path that does not go through the boot; the
# boot INSTALLS explicitly too, because an already-imported module wires
# nothing (ADR-270, the ticket-release precedent).
install_portrait_source(KEY, read_memories, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_memories"]
