"""The interests, as the user portrait reads them (2026-09-16, part B).

Two gates only — the deployment ceiling and the operator switch: the person's
``interests_enabled`` governs the proactive NOTIFICATIONS, not the record they
keep reading. Strongest first over the WHOLE set (SQL orders by the signal
balance), the EXACT total beside the page, the subject when clustering gave
one. A read that fails is ``unavailable``.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.interests.repository import InterestRepository
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    SourceBudget,
    clamp_item,
    empty_section,
    install_portrait_source,
    portrait_lines,
)
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "interests"


async def _allowed() -> bool:
    return bool(settings.interest_extraction_enabled) and await is_capability_enabled(
        PlatformCapability.INTERESTS
    )


async def read_interests(
    *, user_id: UUID, language: str, budget: SourceBudget
) -> PortraitSourceSection:
    """Render the person's active interests for the consolidation prompt.

    Args:
        user_id: The account.
        language: Unused — a topic is stored as the person said it.
        budget: How many items, how long each.

    Returns:
        The section; never raises.
    """
    try:
        if not await _allowed():
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            repo = InterestRepository(db)
            total = await repo.count_active_for_user(user_id)
            rows = (
                await repo.list_active_by_signals(user_id, limit=budget.max_items)
                if total and budget.max_items > 0
                else []
            )
        if not rows:
            return empty_section(KEY, "empty", total=total)
        lines = portrait_lines()
        items = [
            lines["interests_item"].format(
                topic=clamp_item(row.topic or "", budget.item_max_chars),
                category=row.category or "other",
                subject=f", {row.subject}" if row.subject else "",
                weight=f"{int(row.positive_signals or 0) - int(row.negative_signals or 0):+d}",
                last_mentioned=f"{row.last_mentioned_at:%Y-%m-%d}" if row.last_mentioned_at else "",
            )
            for row in rows
        ]
        header = lines["interests_header"].format(shown=len(items), total=total)
        return PortraitSourceSection(
            key=KEY, status="used", text="\n".join([header, *items]), used=len(items), total=total
        )
    except Exception as exc:  # noqa: BLE001 — a blind source is named, never read as empty
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")


#: Where this source's freshness is read (the consolidation's eligibility).
FRESHNESS = FreshnessProbe(table="user_interests", user_column="user_id", stamp_column="updated_at")

# Installed at import for every path that does not go through the boot; the
# boot INSTALLS explicitly too, because an already-imported module wires
# nothing (ADR-270, the ticket-release precedent).
install_portrait_source(KEY, read_interests, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_interests"]
